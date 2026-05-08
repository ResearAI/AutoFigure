"""
AutoFigure Backend Routes
Provides API endpoints for the AutoFigure web interface.
Uses REAL autofigure implementation - NO mock data.
"""

import os
import sys
import uuid
import base64
import threading
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from functools import wraps

from flask import Blueprint, request, jsonify

# Add paths to sys.path for module imports
project_root = Path(__file__).parent.parent
autofigure_path = project_root / 'autofigure'
sys.path.insert(0, str(project_root))

# Import autofigure SDK modules
try:
    from autofigure.generator import (
        generate_initial_code,
        evaluate_code,
        improve_code,
        code_to_png,
        load_reference_figures,
        CONFIG as AUTOFIGURE_CONFIG
    )
    from autofigure.config import Config
    from autofigure.utils.llm_client import LLMClient
    from autofigure.utils.api_protocol import (
        GEMINI_NATIVE,
        chat_completions_url,
        default_base_url,
        normalize_gemini_base_url,
        normalize_protocol,
    )
    from autofigure.enhancer import ImageEnhancer, convert_code_to_text2image_prompt
    AUTOFIGURE_AVAILABLE = True
    ENHANCEMENT_AVAILABLE = True
except ImportError as e:
    print(f"WARNING: AutoFigure module not available: {e}")
    print(f"AutoFigure path: {autofigure_path}")
    AUTOFIGURE_AVAILABLE = False
    ENHANCEMENT_AVAILABLE = False

def extract_methodology(markdown_content: str, config: Dict[str, Any]) -> Optional[str]:
    """
    Extract core methodology from paper content using LLM.
    Uses SDK's LLMClient for API calls.
    """
    if not AUTOFIGURE_AVAILABLE:
        print("[AutoFigure] AutoFigure module not available, skipping methodology extraction")
        return markdown_content

    try:
        # Support both camelCase (from frontend) and snake_case formats
        provider = config.get('methodologyLlmProvider') or config.get('methodology_llm_provider', 'bianxie')
        protocol = config.get('methodologyLlmProtocol') or config.get('methodology_llm_protocol')
        api_key = config.get('methodologyLlmApiKey') or config.get('methodology_llm_api_key', '')
        model = config.get('methodologyLlmModel') or config.get('methodology_llm_model', 'gemini-3.1-pro-preview')
        base_url = config.get('methodologyLlmBaseUrl') or config.get('methodology_llm_base_url', '')
        protocol = normalize_protocol(provider, protocol)

        if not api_key:
            print("[AutoFigure] No methodology LLM API key provided, skipping extraction")
            return markdown_content

        prompt = f"""
        You are a highly discerning AI assistant for academic literature analysis. Your task is to extract ONLY the core theoretical and algorithmic methodology of a scientific paper.

**Core Objective:**
Isolate and extract the section(s) that describe the central innovation of the paper. This section answers the question, "What is the authors' core proposed method, model, or framework?" It should NOT describe how this method was tested or evaluated.

**Guiding Principles & Identification Criteria (What to INCLUDE):**
You must identify and extract the section(s) based on their semantic content. A section should be extracted if it primarily describes:
- The mathematical formulation or theoretical underpinnings of the work.
- The architecture of a novel model or system.
- The steps of a new algorithm.
- The conceptual framework being proposed.
- Common headings include "Method", "Our Approach", "Proposed Model/Framework", "Algorithm".

**Strict Exclusion Criteria (What to EXCLUDE):**
You MUST actively identify and exclude sections that, while related, are not part of the core methodology. DO NOT extract sections primarily describing:
- **Datasets:** Descriptions of data sources, collection methods, or statistics.
- **Experimental Setup:** Details about hardware, software environments, hyperparameters, or implementation specifics.
- **Evaluation Metrics:** Definitions of metrics like Accuracy, F1-Score, PSNR, etc.
- **Results or Ablation Studies:** Any reporting of experimental outcomes.
- Common headings to exclude are "Experiments", "Evaluation", "Dataset", "Implementation Details", "Results".

**Execution Rules:**
1.  **Verbatim Extraction:** Extract the qualifying section(s) verbatim, with original headings. Do not alter the text.
2.  **Boundary Detection:** Start the extraction at the section's heading and stop before a section that should be excluded (e.g., stop before `## Experiments` or `## Results`).
3.  **Output Format:** Produce only the raw Markdown content. Add no commentary.

--- PAPER MARKDOWN START ---
{markdown_content}
--- PAPER MARKDOWN END ---
        """

        print(f"[AutoFigure] Extracting methodology using {provider}/{model}...")

        # Set default base_url based on provider if not specified
        if not base_url:
            base_url = default_base_url(provider, protocol)

        # Create LLMClient with the configuration
        client = LLMClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            provider=provider,
            protocol=protocol,
        )

        response = client.call([prompt])

        if response and len(response.strip()) > 0:
            print(f"[AutoFigure] Methodology extracted, length: {len(response)} characters")
            return response
        else:
            print("[AutoFigure] Methodology extraction returned empty, using original content")
            return markdown_content

    except Exception as e:
        print(f"[AutoFigure] Methodology extraction failed: {e}")
        return markdown_content


def get_reference_figures_for_topic(topic: str) -> List:
    """
    Load reference figures for the specified topic.
    Currently only 'paper' topic has reference figures.

    Returns:
        List of PIL.Image objects for reference figures, or empty list if not available
    """
    if topic != 'paper':
        return []

    # Reference figure paths for 'paper' topic
    # These are the same as used in complete_dataset_experiment.py
    reference_paths = [
        str(autofigure_path / 'references' / 'paper' / 'exp_figure_5.png'),
        str(autofigure_path / 'references' / 'paper' / 'exp_figure_6.png'),
        str(autofigure_path / 'references' / 'paper' / 'exp_figure_7.png'),
        str(autofigure_path / 'references' / 'paper' / 'exp_figure_10.png'),
        str(autofigure_path / 'references' / 'paper' / 'exp_figure_ds.png'),
    ]

    try:
        reference_figures = load_reference_figures(reference_paths)
        print(f"[AutoFigure] Loaded {len(reference_figures)} reference figures for topic '{topic}'")
        return reference_figures
    except Exception as e:
        print(f"[AutoFigure] Failed to load reference figures: {e}")
        return []


# Session storage (in production, use Redis or database)
autofigure_sessions: Dict[str, Dict[str, Any]] = {}
session_locks: Dict[str, threading.Lock] = {}

autofigure_bp = Blueprint('autofigure', __name__, url_prefix='/api/autofigure')


def verify_token(f):
    """Decorator to verify JWT token from Authorization header.

    AutoFigure is a standalone app, so authentication is optional.
    If a token is provided, it will be stored in request.user_token.
    If no token is provided, the request will still be allowed with a default token.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')

        # AutoFigure standalone mode: authentication is optional
        # Always allow access, but store token if provided
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]  # Remove 'Bearer ' prefix
            request.user_token = token if token else 'anonymous'
        else:
            request.user_token = 'anonymous'

        return f(*args, **kwargs)

    return decorated


def get_session_lock(session_id: str) -> threading.Lock:
    """Get or create a lock for the session."""
    if session_id not in session_locks:
        session_locks[session_id] = threading.Lock()
    return session_locks[session_id]


def require_autofigure():
    """Check if autofigure module is available."""
    if not AUTOFIGURE_AVAILABLE:
        return jsonify({
            'error': 'AutoFigure module not available. Please ensure svg_figure_generator.py is properly installed.',
            'autofigure_path': str(autofigure_path)
        }), 503
    return None


def reset_autofigure_config():
    """
    Reset AUTOFIGURE_CONFIG to default values to prevent cross-session pollution.
    This MUST be called at the start of each session's layout generation.

    CRITICAL for multi-user safety: Without this reset, one user's provider settings
    can leak into another user's session, causing authentication failures.
    """
    if not AUTOFIGURE_AVAILABLE:
        return

    # Reset all provider-specific API keys to empty
    AUTOFIGURE_CONFIG['BIANXIE_API_KEY'] = ''
    AUTOFIGURE_CONFIG['OPENROUTER_API_KEY'] = ''
    AUTOFIGURE_CONFIG['GOOGLE_API_KEY'] = ''
    AUTOFIGURE_CONFIG['CLAUDE_API_KEY'] = ''
    AUTOFIGURE_CONFIG['AIGCBEST_API_KEY'] = ''

    # Reset all provider-specific base URLs to their defaults
    AUTOFIGURE_CONFIG['BIANXIE_BASE_URL'] = 'https://api.bianxie.ai/v1'
    AUTOFIGURE_CONFIG['OPENROUTER_BASE_URL'] = 'https://openrouter.ai/api/v1'
    AUTOFIGURE_CONFIG['GEMINI_BASE_URL'] = 'https://generativelanguage.googleapis.com/v1beta'
    AUTOFIGURE_CONFIG['CLAUDE_BASE_URL'] = ''

    # Reset model configurations
    AUTOFIGURE_CONFIG['BIANXIE_CHAT_MODEL'] = 'gemini-3.1-pro-preview'
    AUTOFIGURE_CONFIG['OPENROUTER_MODEL'] = 'google/gemini-3.1-pro-preview'
    AUTOFIGURE_CONFIG['GEMINI_MODEL'] = 'gemini-3.1-pro-preview'
    AUTOFIGURE_CONFIG['CLAUDE_MODEL'] = ''
    AUTOFIGURE_CONFIG['AIGCBEST_CHAT_MODEL'] = ''

    # Reset LLM provider
    AUTOFIGURE_CONFIG['LLM_PROVIDER'] = 'bianxie'
    AUTOFIGURE_CONFIG['LLM_PROTOCOL'] = 'openai-compatible'

    print("[AutoFigure] AUTOFIGURE_CONFIG reset to default values")


def reset_pipeline_config():
    """
    No-op function for backward compatibility.
    With the new SDK-based approach, each request creates fresh LLMClient/ImageEnhancer
    instances, so no global config reset is needed.
    """
    pass


@autofigure_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for AutoFigure."""
    return jsonify({
        'status': 'ok',
        'autofigure_available': AUTOFIGURE_AVAILABLE,
        'enhancement_available': ENHANCEMENT_AVAILABLE,
        'autofigure_path': str(autofigure_path),
        'active_sessions': len(autofigure_sessions)
    })


@autofigure_bp.route('/session/create', methods=['POST'])
@verify_token
def create_session():
    """Create a new AutoFigure session."""
    error = require_autofigure()
    if error:
        return error

    try:
        data = request.get_json()

        config = data.get('config', {})
        input_content = data.get('input_content', '')
        input_type = data.get('input_type', 'text')  # text or pdf

        if not input_content:
            return jsonify({'error': 'Input content is required'}), 400

        # Generate session ID
        session_id = str(uuid.uuid4())

        # Create session data
        session_data = {
            'session_id': session_id,
            'status': 'idle',
            'config': {
                'content_type': config.get('contentType', 'paper'),
                'max_iterations': config.get('maxIterations', 5),
                'quality_threshold': config.get('qualityThreshold', 9.0),
                'min_improvement': config.get('minImprovement', 0.2),
                'human_in_loop': config.get('humanInLoop', True),
                'llm_provider': config.get('llmProvider', 'claude'),
                'llm_protocol': config.get('llmProtocol'),
                'api_key': config.get('apiKey', ''),
                'base_url': config.get('baseUrl', ''),
                'model': config.get('model', ''),
                'svg_width': config.get('svgWidth', 1333),
                'svg_height': config.get('svgHeight', 750),
                # Methodology extraction configuration
                'enable_methodology_extraction': config.get('enableMethodologyExtraction', True),
                'methodology_llm_provider': config.get('methodologyLlmProvider', 'bianxie'),
                'methodology_llm_protocol': config.get('methodologyLlmProtocol'),
                'methodology_llm_api_key': config.get('methodologyLlmApiKey', ''),
                'methodology_llm_base_url': config.get('methodologyLlmBaseUrl', ''),
                'methodology_llm_model': config.get('methodologyLlmModel', 'gemini-3.1-pro-preview'),
                # Enhancement configuration
                'enhancement_mode': config.get('enhancementMode', 'text2image_prompt'),
                'art_style': config.get('artStyle', ''),  # User must provide custom art style
                'enhancement_count': config.get('enhancementCount', 3),
                'enhancement_provider': config.get('enhancementProvider', 'bianxie'),
            },
            'input_content': input_content,
            'input_type': input_type,
            'current_iteration': 0,
            'iterations': [],
            'final_xml': None,
            'enhanced_images': [],
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
        }

        # Store session
        autofigure_sessions[session_id] = session_data

        return jsonify({
            'session_id': session_id,
            'status': 'idle',
            'message': 'Session created successfully'
        })

    except Exception as e:
        return jsonify({'error': f'Failed to create session: {str(e)}'}), 500


@autofigure_bp.route('/session/<session_id>/start', methods=['POST'])
@verify_token
def start_generation(session_id: str):
    """Start the initial figure generation using REAL autofigure."""
    error = require_autofigure()
    if error:
        return error

    try:
        if session_id not in autofigure_sessions:
            return jsonify({'error': 'Session not found'}), 404

        session = autofigure_sessions[session_id]

        with get_session_lock(session_id):
            session['status'] = 'generating'
            session['updated_at'] = datetime.utcnow().isoformat()

        # CRITICAL: Reset configs to prevent cross-session pollution in multi-user environment
        # Reset both AUTOFIGURE_CONFIG (for layout generation) and PIPELINE_CONFIG (for methodology extraction & image generation)
        reset_autofigure_config()
        reset_pipeline_config()

        # Configure autofigure with session config
        config = session['config']

        # SECURITY: Validate that user provided an API key - reject if missing
        if not config.get('api_key'):
            return jsonify({
                'error': 'API key is required. Please provide your API key in the settings.',
                'code': 'API_KEY_REQUIRED'
            }), 400

        AUTOFIGURE_CONFIG['LLM_PROVIDER'] = config['llm_provider']
        AUTOFIGURE_CONFIG['LLM_PROTOCOL'] = normalize_protocol(
            config.get('llm_provider'),
            config.get('llm_protocol'),
        )
        AUTOFIGURE_CONFIG['MAX_ITERATIONS'] = config['max_iterations']
        AUTOFIGURE_CONFIG['QUALITY_THRESHOLD'] = config['quality_threshold']
        AUTOFIGURE_CONFIG['MIN_IMPROVEMENT'] = config['min_improvement']
        AUTOFIGURE_CONFIG['HUMAN_IN_LOOP'] = config['human_in_loop']
        AUTOFIGURE_CONFIG['SVG_WIDTH'] = config['svg_width']
        AUTOFIGURE_CONFIG['SVG_HEIGHT'] = config['svg_height']
        AUTOFIGURE_CONFIG['OUTPUT_FORMAT'] = 'mxgraphxml'  # Always use mxgraphxml for web

        # Set API key based on provider
        if config['api_key']:
            if config['llm_provider'] == 'gemini':
                AUTOFIGURE_CONFIG['GOOGLE_API_KEY'] = config['api_key']
                AUTOFIGURE_CONFIG['GEMINI_BASE_URL'] = (
                    config.get('base_url') or
                    default_base_url('gemini', AUTOFIGURE_CONFIG['LLM_PROTOCOL'])
                )
            elif config['llm_provider'] == 'claude':
                AUTOFIGURE_CONFIG['CLAUDE_API_KEY'] = config['api_key']
                if config['base_url']:
                    AUTOFIGURE_CONFIG['CLAUDE_BASE_URL'] = config['base_url']
            elif config['llm_provider'] == 'openrouter':
                AUTOFIGURE_CONFIG['OPENROUTER_API_KEY'] = config['api_key']
                # OpenRouter uses OpenAI-compatible API, also set as BIANXIE for compatibility
                AUTOFIGURE_CONFIG['BIANXIE_API_KEY'] = config['api_key']
                # Set base URL for OpenRouter
                if config['base_url']:
                    AUTOFIGURE_CONFIG['OPENROUTER_BASE_URL'] = config['base_url']
                    AUTOFIGURE_CONFIG['BIANXIE_BASE_URL'] = config['base_url']
                else:
                    AUTOFIGURE_CONFIG['OPENROUTER_BASE_URL'] = 'https://openrouter.ai/api/v1'
                    AUTOFIGURE_CONFIG['BIANXIE_BASE_URL'] = 'https://openrouter.ai/api/v1'
            elif config['llm_provider'] == 'bianxie':
                AUTOFIGURE_CONFIG['BIANXIE_API_KEY'] = config['api_key']
                if config['base_url']:
                    AUTOFIGURE_CONFIG['BIANXIE_BASE_URL'] = config['base_url']
            elif config['llm_provider'] == 'aigcbest':
                AUTOFIGURE_CONFIG['AIGCBEST_API_KEY'] = config['api_key']
            else:
                # Custom/OpenAI-compatible providers use the BianXie-compatible slot
                # because generator.call_unified_llm resolves unknown providers there.
                AUTOFIGURE_CONFIG['BIANXIE_API_KEY'] = config['api_key']
                AUTOFIGURE_CONFIG['BIANXIE_BASE_URL'] = config.get('base_url') or ''

        if config['model']:
            if config['llm_provider'] == 'gemini':
                AUTOFIGURE_CONFIG['GEMINI_MODEL'] = config['model']
            elif config['llm_provider'] == 'claude':
                AUTOFIGURE_CONFIG['CLAUDE_MODEL'] = config['model']
            elif config['llm_provider'] == 'openrouter':
                AUTOFIGURE_CONFIG['OPENROUTER_MODEL'] = config['model']
                # Also set BIANXIE model for compatibility
                AUTOFIGURE_CONFIG['BIANXIE_CHAT_MODEL'] = config['model']
            elif config['llm_provider'] == 'bianxie':
                AUTOFIGURE_CONFIG['BIANXIE_CHAT_MODEL'] = config['model']
            elif config['llm_provider'] == 'aigcbest':
                AUTOFIGURE_CONFIG['AIGCBEST_CHAT_MODEL'] = config['model']
            else:
                AUTOFIGURE_CONFIG['BIANXIE_CHAT_MODEL'] = config['model']

        # Get input content and apply methodology extraction if content type is 'paper'
        input_content = session['input_content']
        topic = config['content_type']

        print(f"[AutoFigure] Starting generation for session {session_id}")
        print(f"[AutoFigure] Provider: {config['llm_provider']}, Model: {config.get('model', 'N/A')}, Topic: {topic}")
        print(f"[AutoFigure] Base URL: {config.get('base_url', 'default')}")
        print(f"[AutoFigure] AUTOFIGURE_CONFIG BIANXIE_BASE_URL: {AUTOFIGURE_CONFIG.get('BIANXIE_BASE_URL')}")

        # Extract methodology for paper content type (if enabled)
        # Support both camelCase (from frontend) and snake_case formats
        enable_extraction = config.get('enableMethodologyExtraction', config.get('enable_methodology_extraction', True))
        extracted_methodology = None
        if topic == 'paper' and enable_extraction:
            print("[AutoFigure] Extracting methodology from paper content...")
            extracted_methodology = extract_methodology(input_content, config)
            if extracted_methodology and extracted_methodology != input_content:
                print(f"[AutoFigure] Using extracted methodology ({len(extracted_methodology)} chars) instead of full content ({len(input_content)} chars)")
                input_content = extracted_methodology
                # Store extracted methodology in session for reference
                with get_session_lock(session_id):
                    session['extracted_methodology'] = extracted_methodology
            else:
                print("[AutoFigure] Methodology extraction skipped or returned full content")

        # Load reference figures for the topic (currently only 'paper' has reference figures)
        reference_figures = get_reference_figures_for_topic(topic)

        # Store reference figures in session for later use in continue_iteration
        with get_session_lock(session_id):
            session['reference_figures'] = reference_figures

        try:
            xml_code = generate_initial_code(
                paper_content=input_content,
                reference_figures=reference_figures,
                topic=topic,
                output_format='mxgraphxml'
            )
        except Exception as gen_error:
            error_msg = str(gen_error)
            print(f"[AutoFigure] Generation error: {error_msg}", flush=True)
            with get_session_lock(session_id):
                session['status'] = 'error'
                session['error'] = error_msg
            return jsonify({'error': error_msg}), 500

        if not xml_code:
            with get_session_lock(session_id):
                session['status'] = 'error'
                session['error'] = 'Failed to generate initial code - LLM returned empty response'
            return jsonify({'error': 'Failed to generate initial code - LLM returned empty response. Please check your API key and model settings.'}), 500

        # Convert to PNG for preview and evaluation
        png_base64 = None
        current_png = None
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp_path = tmp.name

            success, error_msg = code_to_png(xml_code, tmp_path, attempt_repair=True, output_format='mxgraphxml')

            if success and os.path.exists(tmp_path):
                with open(tmp_path, 'rb') as f:
                    png_base64 = base64.b64encode(f.read()).decode('utf-8')
                # Keep the file open for evaluation
                from PIL import Image
                current_png = Image.open(tmp_path)
            else:
                print(f"[AutoFigure] PNG conversion failed: {error_msg}")
        except Exception as png_error:
            print(f"[AutoFigure] PNG conversion error: {png_error}", flush=True)

        # Evaluate initial code (like continue_iteration does for subsequent iterations)
        evaluation = None
        try:
            print(f"[AutoFigure] Evaluating initial iteration for session {session_id}")
            eval_result = evaluate_code(
                code=xml_code,
                code_image=current_png,
                paper_content=input_content,
                reference_figures=reference_figures,
                iteration=1,
                topic=topic,
                output_format='mxgraphxml'
            )
            quality_score, evaluation = eval_result if eval_result else (0.0, None)
            print(f"[AutoFigure] Initial evaluation complete, score: {quality_score}")
        except Exception as eval_error:
            print(f"[AutoFigure] Initial evaluation error: {eval_error}", flush=True)

        # Clean up
        if current_png:
            current_png.close()
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

        # Store iteration with evaluation
        iteration_data = {
            'iteration': 1,
            'xml': xml_code,
            'png_base64': png_base64,
            'evaluation': evaluation,  # Now includes initial evaluation
            'human_feedback': None,
            'human_score': None,
            'timestamp': datetime.utcnow().isoformat(),
        }

        with get_session_lock(session_id):
            session['iterations'].append(iteration_data)
            session['current_iteration'] = 1
            session['status'] = 'waiting_feedback'
            session['updated_at'] = datetime.utcnow().isoformat()

        print(f"[AutoFigure] Generation complete for session {session_id}")

        return jsonify({
            'session_id': session_id,
            'status': 'waiting_feedback',
            'iteration': 1,
            'xml': xml_code,
            'png_base64': png_base64,
            'evaluation': evaluation,  # Return initial evaluation
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        with get_session_lock(session_id):
            if session_id in autofigure_sessions:
                autofigure_sessions[session_id]['status'] = 'error'
                autofigure_sessions[session_id]['error'] = str(e)
        return jsonify({'error': f'Generation failed: {str(e)}'}), 500


@autofigure_bp.route('/session/<session_id>/continue', methods=['POST'])
@verify_token
def continue_iteration(session_id: str):
    """Continue to the next iteration with optional human feedback using REAL autofigure."""
    error = require_autofigure()
    if error:
        return error

    try:
        if session_id not in autofigure_sessions:
            return jsonify({'error': 'Session not found'}), 404

        session = autofigure_sessions[session_id]
        data = request.get_json()

        current_xml = data.get('current_xml', '')
        human_feedback = data.get('human_feedback')
        human_score = data.get('human_score')

        # Debug: Log received XML details
        print(f"[AutoFigure] Continue request received for session {session_id}", flush=True)
        print(f"[AutoFigure] Received current_xml length: {len(current_xml)}", flush=True)
        print(f"[AutoFigure] Received current_xml first 200 chars: {current_xml[:200] if current_xml else 'EMPTY'}", flush=True)

        if not current_xml:
            return jsonify({'error': 'Current XML is required'}), 400

        # Check iteration limit
        config = session['config']
        if session['current_iteration'] >= config['max_iterations']:
            return jsonify({'error': 'Maximum iterations reached'}), 400

        with get_session_lock(session_id):
            session['status'] = 'generating'
            session['updated_at'] = datetime.utcnow().isoformat()

        # Prepare for evaluation
        input_content = session['input_content']
        topic = config['content_type']

        # Get reference figures from session (loaded during start_generation)
        reference_figures = session.get('reference_figures', [])
        if not reference_figures and topic == 'paper':
            # Reload if not in session (e.g., session restored from storage)
            reference_figures = get_reference_figures_for_topic(topic)

        # Convert XML to PNG for evaluation
        current_png = None
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp_path = tmp.name

            success, _ = code_to_png(current_xml, tmp_path, attempt_repair=True, output_format='mxgraphxml')

            if success and os.path.exists(tmp_path):
                from PIL import Image
                current_png = Image.open(tmp_path)
        except Exception as e:
            print(f"[AutoFigure] Error converting XML to PNG for evaluation: {e}")

        # Evaluate using REAL autofigure
        # evaluate_code signature: (code, code_image, paper_content, reference_figures, iteration, topic, output_format)
        # Returns: Tuple[float, Optional[Dict]]
        print(f"[AutoFigure] Evaluating iteration {session['current_iteration']} for session {session_id}")

        current_iteration = session['current_iteration']
        eval_result = evaluate_code(
            code=current_xml,
            code_image=current_png,
            paper_content=input_content,
            reference_figures=reference_figures,
            iteration=current_iteration,
            topic=topic,
            output_format='mxgraphxml'
        )

        # evaluate_code returns (score, critique_dict)
        quality_score, evaluation = eval_result if eval_result else (0.0, None)

        # Update previous iteration with evaluation
        if session['iterations']:
            prev_iteration = session['iterations'][-1]
            prev_iteration['evaluation'] = evaluation
            prev_iteration['human_feedback'] = human_feedback
            prev_iteration['human_score'] = human_score

        # Check if quality threshold reached
        # Use human score if provided, otherwise use LLM evaluation score
        if human_score is not None:
            quality_score = human_score

        if quality_score >= config['quality_threshold']:
            # Clean up
            if current_png:
                current_png.close()
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

            with get_session_lock(session_id):
                session['status'] = 'waiting_feedback'
                session['updated_at'] = datetime.utcnow().isoformat()

            return jsonify({
                'session_id': session_id,
                'status': 'quality_threshold_reached',
                'iteration': session['current_iteration'],
                'xml': current_xml,
                'evaluation': evaluation,
                'message': 'Quality threshold reached, consider finalizing'
            })

        # Improve code using REAL autofigure
        # improve_code signature: (code, code_image, paper_content, reference_figures, iteration, previous_critique, human_guidance, topic, output_format)
        print(f"[AutoFigure] Improving code for session {session_id}", flush=True)
        print(f"[AutoFigure] Input XML length for improve_code: {len(current_xml)}", flush=True)

        improved_xml = improve_code(
            code=current_xml,
            code_image=current_png,
            paper_content=input_content,
            reference_figures=reference_figures,
            iteration=current_iteration,
            previous_critique=evaluation,
            human_guidance=human_feedback,
            topic=topic,
            output_format='mxgraphxml'
        )

        # Clean up evaluation image
        if current_png:
            current_png.close()
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

        # Debug: Log improve_code result
        print(f"[AutoFigure] improve_code returned: {type(improved_xml)}, length: {len(improved_xml) if improved_xml else 0}", flush=True)

        if not improved_xml:
            # Do NOT silently fall back - return error so user knows improvement failed
            print(f"[AutoFigure] ERROR: improve_code returned None - LLM failed to generate improved XML", flush=True)

            # Clean up resources before returning error
            if current_png:
                current_png.close()
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

            with get_session_lock(session_id):
                session['status'] = 'error'
                session['error'] = 'LLM failed to generate improved diagram. Please try again.'

            return jsonify({
                'error': 'Failed to generate improved diagram. The LLM did not return valid XML. Please try again.',
                'session_id': session_id,
                'status': 'error'
            }), 500

        # Check if improved XML is different from input
        is_same = improved_xml.strip() == current_xml.strip()
        print(f"[AutoFigure] Improved XML same as input: {is_same}", flush=True)
        if is_same:
            print(f"[AutoFigure] WARNING: LLM returned same XML as input!", flush=True)

        # Convert improved XML to PNG
        png_base64 = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp_path = tmp.name

            success, _ = code_to_png(improved_xml, tmp_path, attempt_repair=True, output_format='mxgraphxml')

            if success and os.path.exists(tmp_path):
                with open(tmp_path, 'rb') as f:
                    png_base64 = base64.b64encode(f.read()).decode('utf-8')
                os.unlink(tmp_path)
        except Exception as e:
            print(f"[AutoFigure] Error converting improved XML to PNG: {e}")

        # Store new iteration
        new_iteration = session['current_iteration'] + 1
        iteration_data = {
            'iteration': new_iteration,
            'xml': improved_xml,
            'png_base64': png_base64,
            'evaluation': None,
            'human_feedback': None,
            'human_score': None,
            'timestamp': datetime.utcnow().isoformat(),
        }

        with get_session_lock(session_id):
            session['iterations'].append(iteration_data)
            session['current_iteration'] = new_iteration
            session['status'] = 'waiting_feedback'
            session['updated_at'] = datetime.utcnow().isoformat()

        print(f"[AutoFigure] Iteration {new_iteration} complete for session {session_id}")

        return jsonify({
            'session_id': session_id,
            'status': 'waiting_feedback',
            'iteration': new_iteration,
            'xml': improved_xml,
            'png_base64': png_base64,
            'evaluation': evaluation,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        with get_session_lock(session_id):
            if session_id in autofigure_sessions:
                autofigure_sessions[session_id]['status'] = 'error'
                autofigure_sessions[session_id]['error'] = str(e)
        return jsonify({'error': f'Iteration failed: {str(e)}'}), 500


@autofigure_bp.route('/session/<session_id>/finalize', methods=['POST'])
@verify_token
def finalize_layout(session_id: str):
    """Finalize the layout before beautification."""
    error = require_autofigure()
    if error:
        return error

    try:
        if session_id not in autofigure_sessions:
            return jsonify({'error': 'Session not found'}), 404

        session = autofigure_sessions[session_id]
        data = request.get_json()

        final_xml = data.get('final_xml', '')
        if not final_xml:
            return jsonify({'error': 'Final XML is required'}), 400

        # Convert the user-edited final XML to PNG for preview
        png_base64 = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp_path = tmp.name

            print(f"[AutoFigure] Converting finalized XML to PNG for preview...")
            success, error_msg = code_to_png(final_xml, tmp_path, attempt_repair=True, output_format='mxgraphxml')

            if success and os.path.exists(tmp_path):
                with open(tmp_path, 'rb') as f:
                    png_base64 = base64.b64encode(f.read()).decode('utf-8')
                os.unlink(tmp_path)
                print(f"[AutoFigure] Successfully generated preview PNG from finalized XML")
            else:
                print(f"[AutoFigure] Failed to generate preview PNG: {error_msg}")
        except Exception as png_error:
            print(f"[AutoFigure] Error generating preview PNG: {png_error}")

        with get_session_lock(session_id):
            session['final_xml'] = final_xml
            session['final_png_base64'] = png_base64  # Store the preview of user-edited XML
            session['status'] = 'finalized'
            session['updated_at'] = datetime.utcnow().isoformat()

        return jsonify({
            'session_id': session_id,
            'status': 'finalized',
            'png_base64': png_base64,  # Return the preview image of user-edited XML
            'message': 'Layout finalized, ready for beautification'
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Finalization failed: {str(e)}'}), 500


@autofigure_bp.route('/session/<session_id>/enhance', methods=['POST'])
@verify_token
def start_enhancement(session_id: str):
    """Start the image beautification/enhancement process using REAL implementation."""
    error = require_autofigure()
    if error:
        return error

    try:
        if session_id not in autofigure_sessions:
            return jsonify({'error': 'Session not found'}), 404

        session = autofigure_sessions[session_id]
        data = request.get_json()

        mode = data.get('mode', 'code2prompt')
        art_style = data.get('art_style', session['config']['art_style'])
        variant_count = data.get('variant_count', session['config']['enhancement_count'])

        # User-provided LLM config for code2prompt (required for code2prompt mode)
        enhancement_llm_config = {
            'provider': data.get('enhancement_llm_provider', 'bianxie'),
            'protocol': data.get('enhancement_llm_protocol'),
            'api_key': data.get('enhancement_llm_api_key', ''),
            'base_url': data.get('enhancement_llm_base_url', ''),
            'model': data.get('enhancement_llm_model', 'gemini-3.1-pro-preview'),
        }

        # User-provided image generation config (required)
        image_gen_config = {
            'provider': data.get('image_gen_provider', 'bianxie'),
            'protocol': data.get('image_gen_protocol'),
            'api_key': data.get('image_gen_api_key', ''),
            'base_url': data.get('image_gen_base_url', ''),
            'model': data.get('image_gen_model', ''),
        }

        # Validate required fields
        if not art_style or not art_style.strip():
            return jsonify({'error': 'Art style description is required. Please describe the visual style you want.'}), 400

        if not image_gen_config['api_key']:
            return jsonify({'error': 'Image generation API key is required'}), 400

        if not image_gen_config['model']:
            return jsonify({'error': 'Image generation model is required'}), 400

        if not image_gen_config['base_url']:
            return jsonify({'error': 'Image generation base URL is required'}), 400

        if mode == 'code2prompt' and not enhancement_llm_config['api_key']:
            return jsonify({'error': 'LLM API key is required for code2prompt mode'}), 400

        if not session.get('final_xml'):
            return jsonify({'error': 'Layout must be finalized before enhancement'}), 400

        with get_session_lock(session_id):
            session['status'] = 'enhancing'
            session['enhanced_images'] = [
                {'variant': i + 1, 'status': 'pending', 'pngBase64': None}
                for i in range(variant_count)
            ]
            session['enhancement_config'] = {
                'mode': mode,
                'art_style': art_style,
                'variant_count': variant_count,
                'enhancement_llm_config': enhancement_llm_config,
                'image_gen_config': image_gen_config,
            }
            session['updated_at'] = datetime.utcnow().isoformat()

        # Start enhancement in background thread
        thread = threading.Thread(
            target=_run_enhancement,
            args=(session_id, session['final_xml'], mode, art_style, variant_count,
                  enhancement_llm_config, image_gen_config)
        )
        thread.daemon = True
        thread.start()

        return jsonify({
            'session_id': session_id,
            'status': 'enhancing',
            'message': 'Enhancement started'
        })

    except Exception as e:
        return jsonify({'error': f'Enhancement failed: {str(e)}'}), 500


@autofigure_bp.route('/session/<session_id>/enhance/status', methods=['GET'])
@verify_token
def get_enhancement_status(session_id: str):
    """Get the status of the enhancement process.

    Query params:
        include_images: 'true' to include full image data (default: only on completion)
    """
    try:
        if session_id not in autofigure_sessions:
            return jsonify({'error': 'Session not found'}), 404

        session = autofigure_sessions[session_id]

        enhanced_images = session.get('enhanced_images', [])
        completed = sum(1 for img in enhanced_images if img['status'] == 'completed')
        total = len(enhanced_images)

        progress = int((completed / total * 100)) if total > 0 else 0

        status = 'processing'
        if all(img['status'] in ('completed', 'failed') for img in enhanced_images):
            status = 'completed' if any(img['status'] == 'completed' for img in enhanced_images) else 'failed'
            with get_session_lock(session_id):
                session['status'] = status

        # Only include full image data when completed or explicitly requested
        # This reduces response size during polling (images can be several MB each)
        include_images = request.args.get('include_images', 'false').lower() == 'true'
        is_finished = status in ('completed', 'failed')

        if include_images or is_finished:
            # Include full image data
            response_images = enhanced_images
        else:
            # Only include status info without large base64 data during polling
            response_images = [
                {
                    'variant': img.get('variant'),
                    'status': img.get('status'),
                    'error': img.get('error'),
                    'pngBase64': None  # Omit large data during polling
                }
                for img in enhanced_images
            ]

        return jsonify({
            'session_id': session_id,
            'status': status,
            'progress': progress,
            'completedVariants': completed,
            'totalVariants': total,
            'images': response_images,
        })

    except Exception as e:
        return jsonify({'error': f'Status check failed: {str(e)}'}), 500


@autofigure_bp.route('/session/<session_id>', methods=['GET'])
@verify_token
def get_session(session_id: str):
    """Get full session data."""
    try:
        if session_id not in autofigure_sessions:
            return jsonify({'error': 'Session not found'}), 404

        session = autofigure_sessions[session_id]

        return jsonify({
            'session_id': session['session_id'],
            'status': session['status'],
            'current_iteration': session['current_iteration'],
            'iterations': session['iterations'],
            'final_xml': session.get('final_xml'),
            'enhanced_images': session.get('enhanced_images', []),
            'created_at': session['created_at'],
            'updated_at': session['updated_at'],
        })

    except Exception as e:
        return jsonify({'error': f'Failed to get session: {str(e)}'}), 500


@autofigure_bp.route('/session/<session_id>', methods=['DELETE'])
@verify_token
def delete_session(session_id: str):
    """Delete a session."""
    try:
        if session_id not in autofigure_sessions:
            return jsonify({'error': 'Session not found'}), 404

        del autofigure_sessions[session_id]
        if session_id in session_locks:
            del session_locks[session_id]

        return jsonify({
            'message': 'Session deleted successfully'
        })

    except Exception as e:
        return jsonify({'error': f'Failed to delete session: {str(e)}'}), 500


def _log(msg: str):
    """Log with flush to ensure output in background threads."""
    print(msg, flush=True)
    sys.stdout.flush()


def _run_enhancement(session_id: str, final_xml: str, mode: str, art_style: str,
                     variant_count: int, enhancement_llm_config: Dict[str, Any],
                     image_gen_config: Dict[str, Any]):
    """
    Run enhancement in background thread using SDK classes.

    Modes:
    - 'none': Direct visual enhancement - AI analyzes layout PNG and enhances visually
    - 'code2prompt': First convert mxGraphXML code to text2image prompt via LLM, then enhance

    Args:
        session_id: Session ID
        final_xml: The finalized mxGraphXML code
        mode: 'none' or 'code2prompt'
        art_style: Art style description
        variant_count: Number of variants to generate
        enhancement_llm_config: User-provided LLM config for code2prompt
            - provider: 'gemini', 'claude', 'bianxie', 'openrouter'
            - api_key: API key
            - base_url: Base URL (optional)
            - model: Model name
        image_gen_config: User-provided image generation config
            - provider: 'gemini', 'bianxie', 'openrouter'
            - api_key: API key
            - base_url: Base URL
            - model: Model name
    """
    try:
        session = autofigure_sessions.get(session_id)
        if not session:
            _log(f"[AutoFigure] Session {session_id} not found")
            return

        if not ENHANCEMENT_AVAILABLE:
            _log(f"[AutoFigure] Enhancement module not available")
            for i in range(variant_count):
                with get_session_lock(session_id):
                    session['enhanced_images'][i]['status'] = 'failed'
                    session['enhanced_images'][i]['error'] = 'Enhancement module not available'
            with get_session_lock(session_id):
                session['status'] = 'failed'
            return

        _log(f"[AutoFigure] Starting enhancement for session {session_id}")
        _log(f"[AutoFigure] Mode: {mode}, Art style: {art_style}")
        _log(f"[AutoFigure] LLM Config: provider={enhancement_llm_config.get('provider')}, model={enhancement_llm_config.get('model')}")
        _log(f"[AutoFigure] Image Gen Config: provider={image_gen_config.get('provider')}, model={image_gen_config.get('model')}")

        # Extract LLM config for code2prompt
        llm_provider = enhancement_llm_config.get('provider', 'bianxie')
        llm_protocol = normalize_protocol(llm_provider, enhancement_llm_config.get('protocol'))
        llm_api_key = enhancement_llm_config.get('api_key', '')
        llm_base_url = enhancement_llm_config.get('base_url', '')
        llm_model = enhancement_llm_config.get('model', 'gemini-3.1-pro-preview')

        # Set default base URL for LLM if not specified
        if not llm_base_url:
            llm_base_url = default_base_url(llm_provider, llm_protocol)

        # Extract image generation config
        img_provider = image_gen_config.get('provider', 'bianxie')
        img_protocol = normalize_protocol(img_provider, image_gen_config.get('protocol'))
        img_api_key = image_gen_config.get('api_key', '')
        img_base_url = image_gen_config.get('base_url', '')
        img_model = image_gen_config.get('model', '')

        # Set default base URL for image gen if not specified
        if not img_base_url:
            img_base_url = default_base_url(img_provider, img_protocol)

        # Step 1: Convert final XML to PNG (layout image for enhancement)
        layout_png_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                layout_png_path = tmp.name

            _log(f"[AutoFigure] Converting XML to PNG at: {layout_png_path}")
            success, error_msg = code_to_png(final_xml, layout_png_path, attempt_repair=True, output_format='mxgraphxml')
            if not success:
                _log(f"[AutoFigure] Failed to convert XML to PNG: {error_msg}")
                for i in range(variant_count):
                    with get_session_lock(session_id):
                        session['enhanced_images'][i]['status'] = 'failed'
                        session['enhanced_images'][i]['error'] = f'Layout PNG conversion failed: {error_msg}'
                with get_session_lock(session_id):
                    session['status'] = 'failed'
                return
            _log(f"[AutoFigure] Successfully created layout PNG")
        except Exception as e:
            _log(f"[AutoFigure] Error creating layout PNG: {e}")
            import traceback
            traceback.print_exc()
            for i in range(variant_count):
                with get_session_lock(session_id):
                    session['enhanced_images'][i]['status'] = 'failed'
                    session['enhanced_images'][i]['error'] = str(e)
            with get_session_lock(session_id):
                session['status'] = 'failed'
            return

        # Step 2: Prepare enhancement input based on mode
        enhancement_input = ""
        input_type_for_api = mode

        _log(f"[AutoFigure] Mode: {mode}, XML length: {len(final_xml)} chars")

        if mode == 'code2prompt':
            # Convert mxGraphXML code to text2image prompt using LLM
            _log(f"[AutoFigure] Converting code to text2image prompt...")
            _log(f"[AutoFigure] Using LLM: {llm_provider}/{llm_model}")
            try:
                # Use convert_code_to_text2image_prompt from SDK
                text2image_prompt = convert_code_to_text2image_prompt(
                    source_code=final_xml,
                    art_style=art_style,
                    content_type=session['config'].get('content_type', 'paper'),
                    code_format='mxgraphxml',
                    api_key=llm_api_key,
                    base_url=llm_base_url,
                    model=llm_model,
                    provider=llm_provider,
                    protocol=llm_protocol,
                )

                if text2image_prompt:
                    _log(f"[AutoFigure] Generated prompt length: {len(text2image_prompt)} chars")
                    enhancement_input = text2image_prompt
                    input_type_for_api = 'code2prompt'
                else:
                    _log(f"[AutoFigure] Failed to generate text2image prompt, falling back to none mode")
                    enhancement_input = ""
                    input_type_for_api = 'none'
            except Exception as e:
                _log(f"[AutoFigure] Error converting code to prompt: {e}")
                import traceback
                traceback.print_exc()
                enhancement_input = ""
                input_type_for_api = 'none'
        else:
            # 'none' mode - direct visual enhancement
            _log(f"[AutoFigure] Mode is 'none', skipping code2prompt conversion")
            input_type_for_api = 'none'
            enhancement_input = ""

        _log(f"[AutoFigure] input_type_for_api: {input_type_for_api}")
        _log(f"[AutoFigure] enhancement_input length: {len(enhancement_input)} chars")

        # Step 3: Create Config and ImageEnhancer for enhancement
        enhancement_config = Config(
            enhancement_api_key=img_api_key,
            enhancement_base_url=img_base_url,
            enhancement_model=img_model,
            enhancement_provider=img_provider,
            enhancement_protocol=img_protocol,
            art_style=art_style,
        )
        enhancer = ImageEnhancer(enhancement_config)

        _log(f"[AutoFigure] Generate {variant_count} enhanced images")

        # Step 4: Generate enhanced images
        for i in range(variant_count):
            try:
                with get_session_lock(session_id):
                    session['enhanced_images'][i]['status'] = 'processing'

                _log(f"[AutoFigure] Generating variant {i+1}/{variant_count}...")

                # Create output path for this variant
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    output_path = tmp.name

                # Use ImageEnhancer.enhance() from SDK
                result_path = enhancer.enhance(
                    input_path=layout_png_path,
                    output_path=output_path,
                    enhancement_input=enhancement_input,
                    style=art_style,
                    input_type=input_type_for_api,
                )

                _log(f"[AutoFigure] ImageEnhancer.enhance returned: {result_path}")

                if result_path and os.path.exists(result_path):
                    with open(result_path, 'rb') as f:
                        png_base64 = base64.b64encode(f.read()).decode('utf-8')
                    if result_path != layout_png_path:
                        os.unlink(result_path)

                    with get_session_lock(session_id):
                        session['enhanced_images'][i]['pngBase64'] = png_base64
                        session['enhanced_images'][i]['status'] = 'completed'
                    _log(f"[AutoFigure] Variant {i+1} completed successfully")
                else:
                    if output_path and os.path.exists(output_path):
                        os.unlink(output_path)
                    with get_session_lock(session_id):
                        session['enhanced_images'][i]['status'] = 'failed'
                        session['enhanced_images'][i]['error'] = 'Enhancement returned no result'
                    _log(f"[AutoFigure] Variant {i+1} failed: no result")

            except Exception as e:
                import traceback
                traceback.print_exc()
                _log(f"[AutoFigure] Enhancement variant {i+1} failed: {e}")
                with get_session_lock(session_id):
                    session['enhanced_images'][i]['status'] = 'failed'
                    session['enhanced_images'][i]['error'] = str(e)

        # Clean up layout PNG
        if layout_png_path and os.path.exists(layout_png_path):
            os.unlink(layout_png_path)

        # Update session status
        completed_count = sum(1 for img in session['enhanced_images'] if img['status'] == 'completed')
        with get_session_lock(session_id):
            session['status'] = 'completed' if completed_count > 0 else 'failed'
            session['updated_at'] = datetime.utcnow().isoformat()

        _log(f"[AutoFigure] Enhancement finished: {completed_count}/{variant_count} variants completed")

    except Exception as e:
        import traceback
        traceback.print_exc()
        _log(f"[AutoFigure] Enhancement thread error: {e}")
        with get_session_lock(session_id):
            if session_id in autofigure_sessions:
                autofigure_sessions[session_id]['status'] = 'error'
                autofigure_sessions[session_id]['error'] = str(e)


@autofigure_bp.route('/generate-image', methods=['POST'])
@verify_token
def generate_image():
    """
    Generate an image using user-provided API configuration.
    The generated image will be directly applicable to the draw.io canvas.

    Request body (all fields required):
        prompt: Text description of the image to generate
        provider: API provider ('bianxie' or 'openrouter')
        api_key: User's API key (required)
        model: Model name (required, e.g., gemini-3.1-flash-image-preview)
        base_url: API base URL (required, e.g., https://api.bianxie.ai/v1/chat/completions)

    Returns:
        image_base64: Base64 encoded PNG image
        format: Image format (always 'png')
    """
    import re
    import requests

    _log(f"[AutoFigure] ===== /generate-image endpoint called =====")

    try:
        data = request.get_json()
        _log(f"[AutoFigure] Received request data keys: {list(data.keys()) if data else 'None'}")

        prompt = data.get('prompt', '').strip()
        provider = data.get('provider', 'bianxie').strip().lower()
        protocol = normalize_protocol(provider, data.get('protocol'))
        api_key = data.get('api_key', '').strip()
        model = data.get('model', '').strip()
        base_url = data.get('base_url', '').strip()

        # Validate required fields - all must be provided by user
        if not prompt:
            return jsonify({'error': 'Prompt is required'}), 400
        if not api_key:
            return jsonify({'error': 'API key is required'}), 400
        if not model:
            return jsonify({'error': 'Model is required'}), 400
        if not base_url:
            return jsonify({'error': 'Base URL is required'}), 400

        _log(f"[AutoFigure] Generating image with prompt: {prompt[:100]}...")
        _log(f"[AutoFigure] Using provider: {provider}, protocol: {protocol}, model: {model}, base_url: {base_url}")

        # Build prompt for icon/image generation
        full_prompt = f"""Generate a high-quality image based on the following description.
The image should be suitable for use in a diagram or presentation or scientific paper.
Make sure the image has a clean, transparent or white background when appropriate.

Description: {prompt}

Generate the image now."""

        # Route to provider-specific handling
        if protocol == GEMINI_NATIVE:
            image_base64, image_format = _generate_image_gemini(
                full_prompt, api_key, model, base_url
            )
        elif provider == 'openrouter':
            image_base64, image_format = _generate_image_openrouter(
                full_prompt, api_key, model, base_url
            )
        else:
            # Default/custom OpenAI-compatible path
            image_base64, image_format = _generate_image_bianxie(
                full_prompt, api_key, model, base_url
            )

        if not image_base64:
            return jsonify({'error': 'No image generated'}), 500

        # If not PNG, convert to PNG for consistency
        if image_format != 'png':
            try:
                from PIL import Image
                import io

                image_data = base64.b64decode(image_base64)
                img = Image.open(io.BytesIO(image_data))

                # Convert to PNG
                png_buffer = io.BytesIO()
                img.save(png_buffer, format='PNG')
                image_base64 = base64.b64encode(png_buffer.getvalue()).decode('utf-8')
                image_format = 'png'

                _log(f"[AutoFigure] Converted to PNG, new base64 length: {len(image_base64)}")
            except Exception as conv_error:
                _log(f"[AutoFigure] PNG conversion failed: {conv_error}, using original format")

        return jsonify({
            'image_base64': image_base64,
            'format': image_format,
            'prompt': prompt
        })

    except requests.exceptions.Timeout:
        _log(f"[AutoFigure] Image generation timeout")
        return jsonify({'error': 'Image generation timed out. Please try again.'}), 504
    except Exception as e:
        import traceback
        traceback.print_exc()
        _log(f"[AutoFigure] Image generation error: {e}")
        return jsonify({'error': f'Image generation failed: {str(e)}'}), 500


def _generate_image_bianxie(prompt: str, api_key: str, model: str, base_url: str):
    """
    Generate image using BianXie API.
    BianXie returns images as markdown in content: ![text](data:image/png;base64,...)
    """
    import re
    import requests

    base_url = chat_completions_url(base_url)

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    payload = {
        'model': model,
        'messages': [
            {
                'role': 'user',
                'content': prompt
            }
        ],
        'stream': False
    }

    _log(f"[AutoFigure] BianXie: Sending request to {base_url}")
    _log(f"[AutoFigure] BianXie: Using model: {model}")

    response = requests.post(
        base_url,
        headers=headers,
        json=payload,
        timeout=300
    )

    _log(f"[AutoFigure] BianXie: Response status: {response.status_code}")
    _log(f"[AutoFigure] BianXie: Response headers: {dict(response.headers)}")

    if response.status_code != 200:
        _log(f"[AutoFigure] BianXie API error: {response.status_code} - {response.text[:500]}")
        raise Exception(f'BianXie API request failed: {response.status_code} - {response.text[:200]}')

    # Check if response body is empty
    response_text = response.text
    if not response_text or not response_text.strip():
        _log(f"[AutoFigure] BianXie: Empty response body!")
        raise Exception('BianXie API returned empty response. Check your API key and model name.')

    _log(f"[AutoFigure] BianXie: Response body length: {len(response_text)}")
    _log(f"[AutoFigure] BianXie: Response body preview: {response_text[:500]}")

    # Try to parse JSON with better error handling
    try:
        result = response.json()
    except Exception as json_err:
        _log(f"[AutoFigure] BianXie: JSON parse error: {json_err}")
        _log(f"[AutoFigure] BianXie: Raw response: {response_text[:1000]}")
        raise Exception(f'BianXie API returned invalid JSON. Response: {response_text[:200]}...')

    # Extract image from response
    # BianXie returns images in markdown format: ![text](data:image/[format];base64,[data])
    content = result.get('choices', [{}])[0].get('message', {}).get('content', '')

    if not content:
        _log(f"[AutoFigure] BianXie: No content in response")
        raise Exception('No content in BianXie API response')

    _log(f"[AutoFigure] BianXie: Response content length: {len(content)}")

    # Extract base64 image data using regex
    pattern = r'data:image/(png|jpeg|jpg|webp);base64,([A-Za-z0-9+/=]+)'
    match = re.search(pattern, content)

    if not match:
        _log(f"[AutoFigure] BianXie: No image found in response. Content preview: {content[:300]}")
        raise Exception(f'No image found in BianXie response. Content: {content[:200]}...')

    image_format = match.group(1)
    image_base64 = match.group(2)

    _log(f"[AutoFigure] BianXie: Successfully extracted {image_format} image, base64 length: {len(image_base64)}")

    return image_base64, image_format


def _generate_image_openrouter(prompt: str, api_key: str, model: str, base_url: str):
    """
    Generate image using OpenRouter API.

    Based on OpenRouter API documentation (https://openrouter.ai/google/gemini-3.1-flash-image-preview/api):
    - Requires modalities: ["image", "text"] for image generation
    - Images returned in message.images array as: image['image_url']['url'] (data URL format)

    Example response structure:
    {
        "choices": [{
            "message": {
                "images": [
                    {"image_url": {"url": "data:image/png;base64,..."}}
                ]
            }
        }]
    }
    """
    import requests
    import re

    base_url = chat_completions_url(base_url)

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
        'HTTP-Referer': 'https://localhost',
        'X-Title': 'AutoFigure'
    }

    # OpenRouter requires modalities parameter for image generation
    payload = {
        'model': model,
        'messages': [
            {
                'role': 'user',
                'content': prompt
            }
        ],
        'modalities': ['image', 'text'],
        'stream': False
    }

    _log(f"[AutoFigure] OpenRouter: Sending request to {base_url}")
    _log(f"[AutoFigure] OpenRouter: Using model: {model}")
    _log(f"[AutoFigure] OpenRouter: Request payload keys: {list(payload.keys())}")

    response = requests.post(
        base_url,
        headers=headers,
        json=payload,
        timeout=300
    )

    _log(f"[AutoFigure] OpenRouter: Response status: {response.status_code}")

    if response.status_code != 200:
        _log(f"[AutoFigure] OpenRouter API error: {response.status_code} - {response.text[:500]}")
        raise Exception(f'OpenRouter API request failed: {response.status_code} - {response.text[:200]}')

    # Check if response body is empty
    response_text = response.text
    if not response_text or not response_text.strip():
        _log(f"[AutoFigure] OpenRouter: Empty response body!")
        raise Exception('OpenRouter API returned empty response. Check your API key and model name.')

    _log(f"[AutoFigure] OpenRouter: Response body length: {len(response_text)}")

    # Try to parse JSON with better error handling
    try:
        result = response.json()
    except Exception as json_err:
        _log(f"[AutoFigure] OpenRouter: JSON parse error: {json_err}")
        _log(f"[AutoFigure] OpenRouter: Raw response: {response_text[:1000]}")
        raise Exception(f'OpenRouter API returned invalid JSON. Response: {response_text[:200]}...')

    _log(f"[AutoFigure] OpenRouter: Response keys: {list(result.keys())}")

    # Check for API errors in response
    if 'error' in result:
        error_msg = result.get('error', {})
        if isinstance(error_msg, dict):
            error_msg = error_msg.get('message', str(error_msg))
        _log(f"[AutoFigure] OpenRouter: API error in response: {error_msg}")
        raise Exception(f'OpenRouter API error: {error_msg}')

    # Extract message from choices
    choices = result.get('choices', [])
    if not choices:
        _log(f"[AutoFigure] OpenRouter: No choices in response. Full response: {result}")
        raise Exception('No choices in OpenRouter response')

    message = choices[0].get('message', {})
    _log(f"[AutoFigure] OpenRouter: Message keys: {list(message.keys())}")

    images = message.get('images', [])
    _log(f"[AutoFigure] OpenRouter: Found {len(images)} images in response")

    if images and len(images) > 0:
        # OpenRouter returns images as: {"image_url": {"url": "data:image/png;base64,..."}}
        first_image = images[0]
        _log(f"[AutoFigure] OpenRouter: First image type: {type(first_image)}, structure: {first_image.keys() if isinstance(first_image, dict) else 'not a dict'}")

        # Handle dict format: {"image_url": {"url": "data:..."}}
        if isinstance(first_image, dict):
            image_url_obj = first_image.get('image_url', {})
            if isinstance(image_url_obj, dict):
                image_url = image_url_obj.get('url', '')
            else:
                image_url = str(image_url_obj)
        else:
            # Maybe it's already a string (data URL or base64)
            image_url = str(first_image)

        _log(f"[AutoFigure] OpenRouter: Image URL prefix: {image_url[:100] if image_url else 'empty'}...")

        # Extract base64 from data URL
        if image_url.startswith('data:image/'):
            # Parse data URL: data:image/png;base64,<data>
            pattern = r'data:image/(png|jpeg|jpg|webp);base64,(.+)'
            match = re.match(pattern, image_url)
            if match:
                image_format = match.group(1)
                image_base64 = match.group(2)
                _log(f"[AutoFigure] OpenRouter: Extracted {image_format} image from data URL, base64 length: {len(image_base64)}")
                return image_base64, image_format
            else:
                _log(f"[AutoFigure] OpenRouter: Could not parse data URL format")
        elif image_url:
            # Maybe it's raw base64 without data URL prefix
            _log(f"[AutoFigure] OpenRouter: Image appears to be raw base64, length: {len(image_url)}")
            return image_url, 'png'

    # Fallback: check content for markdown image format (some models may use this)
    content = message.get('content', '')
    if content:
        _log(f"[AutoFigure] OpenRouter: Checking content for embedded images, content length: {len(content)}")
        pattern = r'data:image/(png|jpeg|jpg|webp);base64,([A-Za-z0-9+/=]+)'
        match = re.search(pattern, content)
        if match:
            image_format = match.group(1)
            image_base64 = match.group(2)
            _log(f"[AutoFigure] OpenRouter: Found image in content, base64 length: {len(image_base64)}")
            return image_base64, image_format

    _log(f"[AutoFigure] OpenRouter: No image found. Message: {str(message)[:500]}")
    raise Exception(f'No image found in OpenRouter response. Try a different model that supports image generation.')


def _generate_image_gemini(prompt: str, api_key: str, model: str, base_url: str):
    """
    Generate image using Google Gemini API directly.

    Gemini API uses a different format than OpenAI-compatible APIs:
    - URL: {base_url}/models/{model}:generateContent?key={api_key}
    - Request uses 'contents' with 'parts' instead of 'messages'
    - Response contains 'candidates' with 'content.parts' containing 'inlineData'

    Based on: https://ai.google.dev/gemini-api/docs/image-generation

    Example response structure:
    {
        "candidates": [{
            "content": {
                "parts": [
                    {"text": "Description..."},
                    {"inlineData": {"mimeType": "image/png", "data": "base64..."}}
                ],
                "role": "model"
            }
        }]
    }
    """
    import requests
    import re

    # Construct Gemini API URL
    # Format: {base_url}/models/{model}:generateContent?key={api_key}

    api_url = f"{normalize_gemini_base_url(base_url)}/models/{model}:generateContent?key={api_key}"

    headers = {
        'Content-Type': 'application/json'
    }

    # Gemini API request format
    payload = {
        'contents': [
            {
                'role': 'user',
                'parts': [
                    {'text': prompt}
                ]
            }
        ],
        'generationConfig': {
            'responseModalities': ['image', 'text']
        }
    }

    _log(f"[AutoFigure] Gemini: Sending request to {api_url[:100]}...")
    _log(f"[AutoFigure] Gemini: Using model: {model}")

    response = requests.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=300
    )

    _log(f"[AutoFigure] Gemini: Response status: {response.status_code}")

    if response.status_code != 200:
        _log(f"[AutoFigure] Gemini API error: {response.status_code} - {response.text[:500]}")
        raise Exception(f'Gemini API request failed: {response.status_code} - {response.text[:200]}')

    # Check if response body is empty
    response_text = response.text
    if not response_text or not response_text.strip():
        _log(f"[AutoFigure] Gemini: Empty response body!")
        raise Exception('Gemini API returned empty response. Check your API key and model name.')

    _log(f"[AutoFigure] Gemini: Response body length: {len(response_text)}")

    # Try to parse JSON
    try:
        result = response.json()
    except Exception as json_err:
        _log(f"[AutoFigure] Gemini: JSON parse error: {json_err}")
        _log(f"[AutoFigure] Gemini: Raw response: {response_text[:1000]}")
        raise Exception(f'Gemini API returned invalid JSON. Response: {response_text[:200]}...')

    _log(f"[AutoFigure] Gemini: Response keys: {list(result.keys())}")

    # Check for API errors
    if 'error' in result:
        error_msg = result.get('error', {})
        if isinstance(error_msg, dict):
            error_msg = error_msg.get('message', str(error_msg))
        _log(f"[AutoFigure] Gemini: API error: {error_msg}")
        raise Exception(f'Gemini API error: {error_msg}')

    # Extract from candidates
    candidates = result.get('candidates', [])
    if not candidates:
        _log(f"[AutoFigure] Gemini: No candidates in response")
        raise Exception('No candidates in Gemini response')

    content = candidates[0].get('content', {})
    parts = content.get('parts', [])

    _log(f"[AutoFigure] Gemini: Found {len(parts)} parts in response")

    # Look for inlineData (image) in parts
    for part in parts:
        if 'inlineData' in part:
            inline_data = part['inlineData']
            mime_type = inline_data.get('mimeType', 'image/png')
            image_data = inline_data.get('data', '')

            if image_data:
                # Extract format from mime type
                if 'png' in mime_type:
                    image_format = 'png'
                elif 'jpeg' in mime_type or 'jpg' in mime_type:
                    image_format = 'jpeg'
                elif 'webp' in mime_type:
                    image_format = 'webp'
                else:
                    image_format = 'png'

                _log(f"[AutoFigure] Gemini: Found {image_format} image, base64 length: {len(image_data)}")
                return image_data, image_format

    # Fallback: check for data URL in text parts
    for part in parts:
        if 'text' in part:
            text = part['text']
            pattern = r'data:image/(png|jpeg|jpg|webp);base64,([A-Za-z0-9+/=]+)'
            match = re.search(pattern, text)
            if match:
                image_format = match.group(1)
                image_base64 = match.group(2)
                _log(f"[AutoFigure] Gemini: Found image in text content, base64 length: {len(image_base64)}")
                return image_base64, image_format

    _log(f"[AutoFigure] Gemini: No image found in response. Parts: {str(parts)[:500]}")
    raise Exception('No image found in Gemini response. Make sure the model supports image generation.')


def register_autofigure_routes(app):
    """Register AutoFigure routes with Flask app."""
    app.register_blueprint(autofigure_bp)
    print(f"[AutoFigure] Routes registered, module available: {AUTOFIGURE_AVAILABLE}")
