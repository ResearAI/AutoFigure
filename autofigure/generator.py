import os
import json
import time
import base64
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from PIL import Image
import io
import cairosvg
import re
import webbrowser
from openai import OpenAI

from .utils.api_protocol import (
    GEMINI_NATIVE,
    call_gemini_native_text,
    default_base_url,
    normalize_openai_base_url,
    normalize_protocol,
)


CONFIG = {
    'MAX_ITERATIONS': 5,
    'QUALITY_THRESHOLD': 9.0,
    'MIN_IMPROVEMENT': 0.2,

    # =========================
    # Output Format Selection
    # =========================
    # 'svg': SVG vector graphics (default, works with cairosvg for PNG conversion)
    # 'mxgraphxml': mxGraph XML format (compatible with draw.io/next-ai-draw-io)
    'OUTPUT_FORMAT': 'svg',  # Choose: 'svg' | 'mxgraphxml'

    # =========================
    # LLM Configuration
    # =========================
    'LLM_PROVIDER': 'openrouter',  # openrouter, bianxie, gemini
    'LLM_PROTOCOL': 'openai-compatible',  # openai-compatible, gemini-native

    # OpenRouter
    'OPENROUTER_BASE_URL': 'https://openrouter.ai/api/v1',
    'OPENROUTER_API_KEY': '',
    'OPENROUTER_MODEL': 'google/gemini-3.1-pro-preview',

    # Bianxie
    'BIANXIE_BASE_URL': 'https://api.bianxie.ai/v1',
    'BIANXIE_API_KEY': '',
    'BIANXIE_CHAT_MODEL': 'gemini-3.1-pro-preview',

    # Gemini
    'GEMINI_BASE_URL': 'https://generativelanguage.googleapis.com/v1beta/openai/',
    'GOOGLE_API_KEY': '',
    'GEMINI_MODEL': 'gemini-3.1-pro-preview',

    'SVG_WIDTH': 1333,             # SVG width
    'SVG_HEIGHT': 750,             # SVG height
    'OUTPUT_DIR': './autofigure_output',    # Output directory
    'MAX_REPAIR_RETRIES': 2,       # Maximum retries for repair functions
    'SUPPORTED_TOPICS': ['paper', 'survey', 'blog', 'textbook'],  # Supported content types
    'HUMAN_IN_LOOP': False,
    'AUTO_OPEN_IMAGES': False
}


def update_config_from_sdk(sdk_config) -> None:
    """
    Update CONFIG from SDK Config object.

    Args:
        sdk_config: autofigure.config.Config object
    """
    global CONFIG

    # LLM settings based on provider
    provider = sdk_config.generation_provider
    protocol = sdk_config.generation_protocol or normalize_protocol(provider)
    CONFIG['LLM_PROVIDER'] = provider
    CONFIG['LLM_PROTOCOL'] = protocol

    if provider == 'openrouter':
        CONFIG['OPENROUTER_API_KEY'] = sdk_config.generation_api_key
        CONFIG['OPENROUTER_BASE_URL'] = sdk_config.generation_base_url or 'https://openrouter.ai/api/v1'
        CONFIG['OPENROUTER_MODEL'] = sdk_config.generation_model or 'google/gemini-3.1-pro-preview'
    elif provider == 'bianxie':
        CONFIG['BIANXIE_API_KEY'] = sdk_config.generation_api_key
        CONFIG['BIANXIE_BASE_URL'] = sdk_config.generation_base_url or 'https://api.bianxie.ai/v1'
        CONFIG['BIANXIE_CHAT_MODEL'] = sdk_config.generation_model or 'gemini-3.1-pro-preview'
    elif provider == 'gemini':
        CONFIG['GOOGLE_API_KEY'] = sdk_config.generation_api_key
        CONFIG['GEMINI_BASE_URL'] = sdk_config.generation_base_url or default_base_url(provider, protocol)
        CONFIG['GEMINI_MODEL'] = sdk_config.generation_model or 'gemini-3.1-pro-preview'
    else:
        CONFIG['BIANXIE_API_KEY'] = sdk_config.generation_api_key
        CONFIG['BIANXIE_BASE_URL'] = sdk_config.generation_base_url or default_base_url(provider, protocol) or ''
        CONFIG['BIANXIE_CHAT_MODEL'] = sdk_config.generation_model or 'gemini-3.1-pro-preview'

    # Pipeline settings
    CONFIG['MAX_ITERATIONS'] = sdk_config.max_iterations
    CONFIG['QUALITY_THRESHOLD'] = sdk_config.quality_threshold
    CONFIG['MIN_IMPROVEMENT'] = sdk_config.min_improvement
    CONFIG['OUTPUT_DIR'] = sdk_config.output_dir

    # Always disable human-in-loop for SDK usage
    CONFIG['HUMAN_IN_LOOP'] = False
    CONFIG['AUTO_OPEN_IMAGES'] = False

def call_unified_llm(contents: List[Any], provider: Optional[str] = None,
                     api_key: Optional[str] = None, model: Optional[str] = None,
                     base_url: Optional[str] = None,
                     protocol: Optional[str] = None) -> Optional[str]:
    """
    Unified LLM call interface - supports multiple providers (bianxie, openrouter, gemini)

    IMPORTANT: This function MUST respect the provider parameter and CONFIG settings.
    User-provided credentials should ALWAYS take precedence.

    Args:
        contents: List of content (text and images)
        provider: LLM provider ('bianxie', 'openrouter', or 'gemini'), defaults from CONFIG
        api_key: API key (REQUIRED - must be provided by user or CONFIG)
        model: Model name (defaults from CONFIG based on provider)
        base_url: API base URL (defaults from CONFIG based on provider)

    Returns:
        LLM response text, None on failure
    """
    # Determine the actual provider from parameter or CONFIG
    actual_provider = provider or CONFIG.get('LLM_PROVIDER', 'bianxie')
    actual_protocol = normalize_protocol(actual_provider, protocol or CONFIG.get('LLM_PROTOCOL'))

    # Determine base_url, api_key, model based on provider
    if actual_provider == 'gemini':
        actual_api_key = api_key or CONFIG.get('GOOGLE_API_KEY')
        actual_model = model or CONFIG.get('GEMINI_MODEL') or 'gemini-3.1-pro-preview'
        actual_base_url = base_url or CONFIG.get('GEMINI_BASE_URL')
        if not actual_base_url:
            actual_base_url = default_base_url(actual_provider, actual_protocol)
    elif actual_provider == 'openrouter':
        actual_base_url = base_url or CONFIG.get('OPENROUTER_BASE_URL') or CONFIG.get('BIANXIE_BASE_URL')
        actual_api_key = api_key or CONFIG.get('OPENROUTER_API_KEY') or CONFIG.get('BIANXIE_API_KEY')
        actual_model = model or CONFIG.get('OPENROUTER_MODEL') or CONFIG.get('BIANXIE_CHAT_MODEL')
        # Default OpenRouter URL if nothing is set
        if not actual_base_url:
            actual_base_url = 'https://openrouter.ai/api/v1'
    else:  # bianxie or default
        actual_base_url = base_url or CONFIG.get('BIANXIE_BASE_URL')
        actual_api_key = api_key or CONFIG.get('BIANXIE_API_KEY')
        actual_model = model or CONFIG.get('BIANXIE_CHAT_MODEL')
        # Default Bianxie URL if nothing is set
        if not actual_base_url:
            actual_base_url = default_base_url(actual_provider, actual_protocol) or 'https://api.bianxie.ai/v1'

    # Debug logging
    print(f"[svg_figure_generator.call_unified_llm] provider: {actual_provider}")
    print(f"[svg_figure_generator.call_unified_llm] protocol: {actual_protocol}")
    print(f"[svg_figure_generator.call_unified_llm] base_url: {actual_base_url}")
    print(f"[svg_figure_generator.call_unified_llm] model: {actual_model}")
    print(f"[svg_figure_generator.call_unified_llm] api_key present: {bool(actual_api_key)}, suffix: {'...' + actual_api_key[-4:] if actual_api_key and len(actual_api_key) > 4 else 'N/A'}")

    if actual_protocol == GEMINI_NATIVE:
        return call_gemini_native_text(contents, actual_api_key, actual_model, actual_base_url)

    actual_base_url = normalize_openai_base_url(actual_base_url)
    return _call_openai_compatible(contents, actual_api_key, actual_model, actual_base_url)


def _call_openai_compatible(contents: List[Any], api_key: Optional[str] = None,
                            model: Optional[str] = None, base_url: Optional[str] = None) -> Optional[str]:
    """
    Call OpenAI-compatible API (works with bianxie, openrouter, etc.)

    IMPORTANT: This function requires api_key, model, and base_url to be passed.
    It should NOT have any hardcoded fallback values for security reasons.

    Args:
        contents: List of content (text and images)
        api_key: API key (REQUIRED)
        model: Model name (REQUIRED)
        base_url: API base URL (REQUIRED)

    Returns:
        LLM response text, or None on failure
    """
    try:
        # Validate required parameters
        if not api_key:
            print('[svg_figure_generator._call_openai_compatible] ERROR: API key not provided!')
            print('[svg_figure_generator._call_openai_compatible] User must provide their own API key.')
            return None

        if not model:
            print('[svg_figure_generator._call_openai_compatible] ERROR: Model not specified!')
            return None

        if not base_url:
            print('[svg_figure_generator._call_openai_compatible] ERROR: Base URL not specified!')
            return None

        print(f"[svg_figure_generator._call_openai_compatible] Making API call to: {base_url}")
        print(f"[svg_figure_generator._call_openai_compatible] Using model: {model}")

        client = OpenAI(base_url=base_url, api_key=api_key)

        message_content: List[Dict[str, Any]] = []
        for part in contents:
            if isinstance(part, str):
                message_content.append({"type": "text", "text": part})
            elif isinstance(part, Image.Image):
                buf = io.BytesIO()
                part.save(buf, format='PNG')
                image_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                message_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"}
                })
            else:
                print(f"Skipping unsupported content type: {type(part)}")

        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": message_content}]
        )

        result = completion.choices[0].message.content if completion and completion.choices else None
        return result
    except Exception as e:
        error_msg = str(e)
        print(f"[svg_figure_generator._call_openai_compatible] API call failed: {error_msg}")

        # Provide more specific error messages for common issues
        if "401" in error_msg or "Unauthorized" in error_msg:
            raise Exception(f"API authentication failed (401 Unauthorized). Please check your API key for {base_url}. Error: {error_msg}")
        elif "403" in error_msg or "Forbidden" in error_msg:
            raise Exception(f"API access forbidden (403). Your API key may not have permission for this model. Error: {error_msg}")
        elif "429" in error_msg or "rate limit" in error_msg.lower():
            raise Exception(f"API rate limit exceeded. Please wait and try again. Error: {error_msg}")
        elif "timeout" in error_msg.lower():
            raise Exception(f"API request timed out. The server may be overloaded. Error: {error_msg}")
        else:
            raise Exception(f"LLM API call failed: {error_msg}")


# Backward compatibility alias - DEPRECATED, use call_unified_llm instead
def _call_bianxie_chat(contents: List[Any], api_key: Optional[str] = None,
                       model: Optional[str] = None) -> Optional[str]:
    """DEPRECATED: Use call_unified_llm instead. This is kept for backward compatibility."""
    return call_unified_llm(contents, provider='bianxie', api_key=api_key, model=model)


def call_google_genai_multimodal(contents: List, api_key: str = None) -> Optional[str]:
    """
    Legacy function name kept for compatibility.
    Routes to call_unified_llm using CONFIG settings.
    """
    return call_unified_llm(contents, api_key=api_key)

def read_paper_content(paper_path: str) -> str:
    try:
        with open(paper_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"Successfully read paper content: {len(content)} characters")
        return content
    except Exception as e:
        print(f"Failed to read paper file: {e}")
        return ""

def load_reference_figures(figure_paths: List[str]) -> List[Image.Image]:
    reference_figures = []
    for i, path in enumerate(figure_paths):
        try:
            img = Image.open(path)
            reference_figures.append(img)
            print(f"Successfully loaded reference figure {i+1}: {path}")
        except Exception as e:
            print(f"Failed to load reference figure {path}: {e}")
    
    return reference_figures

def get_initial_prompt_template(topic: str, content: str, output_format: str = None) -> str:
    if topic not in CONFIG['SUPPORTED_TOPICS']:
        raise ValueError(f"Unsupported topic: {topic}. Supported topics are: {CONFIG['SUPPORTED_TOPICS']}")

    output_format = output_format or CONFIG.get('OUTPUT_FORMAT', 'svg')

    common_placeholder_spec = """
**Placeholder Specification:**
    *   To prepare for final illustration, an icon needs a placeholder.
    *   **Function**: The placeholder's role is to reserve space and provide a clear directive for the illustrator.
    *   **Recommended Implementation**: A clean, professional way to do this is with a gray, rounded-corner rectangle (`<rect rx="8" ry="8" style="fill:#cccccc; stroke:#666666; stroke-width:1;" />`).
    *   **Content (CRITICAL)**: Each placeholder MUST contain two pieces of text:
        *   **Exterior Label**: A concise name for the component, placed **outside** the box (e.g., above it).
        *   **Interior Description**: A detailed English phrase describing the desired icon using the format `[icon]: <description>`, placed **inside** the box (e.g., `[icon]: An icon showing a robot meticulously reviewing a paper`). This description MUST NOT appear in the final illustration but is a crucial instruction and it must be detailed and concrete.
"""

    # Select appropriate prompt template based on output format
    if output_format == 'mxgraphxml':
        if topic == 'paper':
            return _get_paper_mxgraphxml_prompt_template(content, common_placeholder_spec)
        elif topic == 'survey':
            return _get_survey_mxgraphxml_prompt_template(content, common_placeholder_spec)
        elif topic == 'blog':
            return _get_blog_mxgraphxml_prompt_template(content, common_placeholder_spec)
        elif topic == 'textbook':
            return _get_textbook_mxgraphxml_prompt_template(content, common_placeholder_spec)
    else:  # default to svg
        if topic == 'paper':
            return _get_paper_prompt_template(content, common_placeholder_spec)
        elif topic == 'survey':
            return _get_survey_prompt_template(content, common_placeholder_spec)
        elif topic == 'blog':
            return _get_blog_prompt_template(content, common_placeholder_spec)
        elif topic == 'textbook':
            return _get_textbook_prompt_template(content, common_placeholder_spec)

def extract_layout_type(svg_code: str) -> Optional[str]:
    try:
        match = re.search(r"<!--\s*LAYOUT_TYPE:\s*([a-zA-Z0-9_\-]+)\s*-->", svg_code)
        if match:
            return match.group(1).strip().lower()
        return None
    except Exception:
        return None

def _get_paper_prompt_template(content: str, placeholder_spec: str) -> str:
    """Returns the complex prompt template for research papers."""
    return f"""
You are a top-tier scientific figure layout designer. Please write SVG code based on the following paper content to visualize the core method the paper proposes as clear illustrations.

**Placeholder Specification:**
    *   To prepare for final illustration, an icon needs a placeholder.
    *   **Function**: The placeholder's role is to reserve space and provide a clear directive for the illustrator.
    *   **Recommended Implementation**: A clean, professional way to do this is with a gray, rounded-corner rectangle (`<rect rx="8" ry="8" style="fill:#cccccc; stroke:#666666; stroke-width:1;" />`).
    *   **Content (CRITICAL)**: Each placeholder MUST contain two pieces of text:
        *   **Exterior Label**: A concise name for the component, placed **outside** the box (e.g., above it).
        *   **Interior Description**: A detailed English phrase describing the desired icon using the format `[icon]: <description>`, placed **inside** the box (e.g., `[icon]: An icon showing a robot meticulously reviewing a paper`). This description MUST NOT appear in the final illustration but is a crucial instruction and it must be detailed and concrete.

Additional Suggestions:
1. Add more texts and examples to server as the supplementary information to make the layout more readable and easy to understand

**Paper Content:**
{content}

**Reference Figures:**
(You have been provided with reference images to inspire the design.)

**Final Output Requirement:**
A single block of SVG code that is aesthetically superb and tells a clear, compelling story of the paper's methodology.
"""

def _get_survey_prompt_template(content: str, placeholder_spec: str) -> str:
    """Returns the complex prompt template for survey papers."""
    return f"""
You are a top-tier survey visualization expert. Please write SVG code based on the following survey content to visualize the comprehensive knowledge structure and field organization as clear illustrations.

The common survey figure types include: Taxonomy/Classification Hierarchy, Conceptual Framework/Flowchart, Multi-Panel/Modular Diagram, Cycle/Relational Diagram, Pyramid/Hierarchy Diagram, Comparison Figure, Evolutionary Diagram, Timeline, Table of Contents, etc.

**Placeholder Specification:**
    *   To prepare for final illustration, an icon needs a placeholder.
    *   **Function**: The placeholder's role is to reserve space and provide a clear directive for the illustrator.
    *   **Recommended Implementation**: A clean, professional way to do this is with a gray, rounded-corner rectangle (`<rect rx="8" ry="8" style="fill:#cccccc; stroke:#666666; stroke-width:1;" />`).
    *   **Content (CRITICAL)**: Each placeholder MUST contain two pieces of text:
        *   **Exterior Label**: A concise name for the component, placed **outside** the box (e.g., above it).
        *   **Interior Description**: A detailed English phrase describing the desired icon using the format `[icon]: <description>`, placed **inside** the box (e.g., `[icon]: An icon showing a robot meticulously reviewing a paper`). This description MUST NOT appear in the final illustration but is a crucial instruction and it must be detailed and concrete.

Additional Suggestions:
1. Add more texts and examples to server as the supplementary information to make the layout more readable and easy to understand

**Survey Content:**
{content}

**Reference Figures:**
(You have been provided with excellent examples of modern survey visualizations demonstrating current best practices in academic knowledge mapping and field organization.)

**Final Output Requirement:**
A single block of SVG code that is aesthetically superb and tells a clear, compelling story of the survey's comprehensive knowledge structure and field organization.
"""

def _get_blog_prompt_template(content: str, placeholder_spec: str) -> str:
    """Returns the complex prompt template for blog posts."""
    return f"""
You are a top-tier educational illustration expert. Please write SVG code based on the following blog content to visualize the educational concepts and technical knowledge as clear illustrations.

**Placeholder Specification:**
    *   To prepare for final illustration, an icon needs a placeholder.
    *   **Function**: The placeholder's role is to reserve space and provide a clear directive for the illustrator.
    *   **Recommended Implementation**: A clean, professional way to do this is with a gray, rounded-corner rectangle (`<rect rx="8" ry="8" style="fill:#cccccc; stroke:#666666; stroke-width:1;" />`).
    *   **Content (CRITICAL)**: Each placeholder MUST contain two pieces of text:
        *   **Exterior Label**: A concise name for the component, placed **outside** the box (e.g., above it).
        *   **Interior Description**: A detailed English phrase describing the desired icon using the format `[icon]: <description>`, placed **inside** the box (e.g., `[icon]: An icon showing a robot meticulously reviewing a paper`). This description MUST NOT appear in the final illustration but is a crucial instruction and it must be detailed and concrete.

Additional Suggestions:
1. Add more details (eg. some examples) to better explain the blog's content.
2. Make the layout orderly and avoid components overlapping (especially lines).

**Blog Content:**
{content}

**Reference Figures:**
(You have been provided with reference blog illustrations showing how to explain technical concepts visually.)

**Final Output Requirement:**
A single block of SVG code that is aesthetically superb and tells a clear, compelling story of the blog's educational concepts and technical knowledge.
"""

def _get_textbook_prompt_template(content: str, placeholder_spec: str) -> str:
    """Returns the complex prompt template for textbook content."""
    return f"""
You are a top-tier educational visualization designer. Please write SVG code based on the following textbook content to visualize the pedagogical concepts and knowledge structure as clear illustrations.

**Placeholder Specification:**
    *   To prepare for final illustration, an icon needs a placeholder.
    *   **Function**: The placeholder's role is to reserve space and provide a clear directive for the illustrator.
    *   **Recommended Implementation**: A clean, professional way to do this is with a gray, rounded-corner rectangle (`<rect rx="8" ry="8" style="fill:#cccccc; stroke:#666666; stroke-width:1;" />`).
    *   **Content (CRITICAL)**: Each placeholder MUST contain two pieces of text:
        *   **Exterior Label**: A concise name for the component, placed **outside** the box (e.g., above it).
        *   **Interior Description**: A detailed English phrase describing the desired icon using the format `[icon]: <description>`, placed **inside** the box (e.g., `[icon]: An icon showing a robot meticulously reviewing a paper`). This description MUST NOT appear in the final illustration but is a crucial instruction and it must be detailed and concrete.

Additional Suggestions:
1. Add more details (eg. some examples) to better explain the textbook's content.
2. Make the layout orderly and avoid components overlapping (especially lines).

**Textbook Content:**
{content}

**Reference Figures:**
(You have been provided with reference images to inspire the design.)

**Final Output Requirement:**
A single block of SVG code that is aesthetically superb and tells a clear, compelling story of the textbook's pedagogical concepts and knowledge structure.
"""


# =========================
# mxGraph XML Prompt Templates (for draw.io compatibility)
# =========================

def _get_mxgraphxml_placeholder_spec() -> str:
    """Returns placeholder specification adapted for mxGraph XML format."""
    return """
**Placeholder Specification for mxGraph XML:**
    *   To prepare for final illustration, an icon needs a placeholder.
    *   **Function**: The placeholder's role is to reserve space and provide a clear directive for the illustrator.
    *   **Recommended Implementation**: Use an mxCell with a gray rounded rectangle style:
        `<mxCell value="" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#CCCCCC;strokeColor=#666666;" vertex="1" parent="1">`
    *   **Content (CRITICAL)**: Each placeholder MUST have:
        *   **Exterior Label**: A concise name for the component in a separate mxCell placed above/beside the placeholder.
        *   **Interior Description**: The mxCell's `value` attribute should contain a detailed description using the format `[icon]: <description>` (e.g., `[icon]: An icon showing a robot meticulously reviewing a paper`).
"""

def _get_paper_mxgraphxml_prompt_template(content: str, placeholder_spec: str) -> str:
    """Returns the mxGraph XML prompt template for research papers."""
    return f"""
You are a top-tier scientific figure layout designer. Please write mxGraph XML code (draw.io format) based on the following paper content to visualize the core method the paper proposes as clear illustrations.

**CRITICAL FORMAT REQUIREMENTS:**
You MUST output valid mxGraph XML code that follows this exact structure:
```xml
<mxfile>
  <diagram name="Page-1" id="page-1">
    <mxGraphModel dx="1" dy="1" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{CONFIG.get('SVG_WIDTH', 1333)}" pageHeight="{CONFIG.get('SVG_HEIGHT', 750)}" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <!-- Your diagram elements here -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

**mxCell Element Rules:**
- All elements are mxCell tags as DIRECT children of <root>
- Every mxCell (except id="0") MUST have a `parent` attribute
- Shapes: `<mxCell value="label" style="..." vertex="1" parent="1"><mxGeometry x="..." y="..." width="..." height="..." as="geometry"/></mxCell>`
- Edges: `<mxCell edge="1" parent="1" source="sourceId" target="targetId"><mxGeometry relative="1" as="geometry"/></mxCell>`
- Use unique `id` attributes for each mxCell (e.g., "cell-1", "cell-2", etc.)

**Common Styles:**
- Rectangle: `rounded=0;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#000000;`
- Rounded Rectangle: `rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#000000;`
- Ellipse: `ellipse;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#000000;`
- Text: `text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;`
- Arrow: `edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;`

{_get_mxgraphxml_placeholder_spec()}

**Color Restriction**: The diagram MUST only use black, white, and gray colors—no other colors allowed.

**Placeholder Sizing**: Placeholders MUST use flexible sizes that adapt to the layout—avoid uniform sizes; each placeholder should be sized appropriately based on its content importance and position in the layout.

Additional Suggestions:
1. Add more texts and examples to serve as supplementary information to make the layout more readable and easy to understand
2. Keep all x coordinates in range [0, {CONFIG.get('SVG_WIDTH', 1333)}] and y coordinates in range [0, {CONFIG.get('SVG_HEIGHT', 750)}]

**Paper Content:**
{content}

**Reference Figures:**
(You have been provided with reference images to inspire the design.)

**Final Output Requirement:**
A single block of mxGraph XML code (starting with <mxfile> and ending with </mxfile>) that is aesthetically superb and tells a clear, compelling story of the paper's methodology.
"""

def _get_survey_mxgraphxml_prompt_template(content: str, placeholder_spec: str) -> str:
    """Returns the mxGraph XML prompt template for survey papers."""
    return f"""
You are a top-tier survey visualization expert. Please write mxGraph XML code (draw.io format) based on the following survey content to visualize the comprehensive knowledge structure and field organization as clear illustrations.

The common survey figure types include: Taxonomy/Classification Hierarchy, Conceptual Framework/Flowchart, Multi-Panel/Modular Diagram, Cycle/Relational Diagram, Pyramid/Hierarchy Diagram, Comparison Figure, Evolutionary Diagram, Timeline, Table of Contents, etc.

**CRITICAL FORMAT REQUIREMENTS:**
You MUST output valid mxGraph XML code that follows this exact structure:
```xml
<mxfile>
  <diagram name="Page-1" id="page-1">
    <mxGraphModel dx="1" dy="1" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{CONFIG.get('SVG_WIDTH', 1333)}" pageHeight="{CONFIG.get('SVG_HEIGHT', 750)}" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <!-- Your diagram elements here -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

**mxCell Element Rules:**
- All elements are mxCell tags as DIRECT children of <root>
- Every mxCell (except id="0") MUST have a `parent` attribute
- Shapes: `<mxCell value="label" style="..." vertex="1" parent="1"><mxGeometry x="..." y="..." width="..." height="..." as="geometry"/></mxCell>`
- Edges: `<mxCell edge="1" parent="1" source="sourceId" target="targetId"><mxGeometry relative="1" as="geometry"/></mxCell>`
- Use unique `id` attributes for each mxCell

{_get_mxgraphxml_placeholder_spec()}

**Color Restriction**: The diagram MUST only use black, white, and gray colors—no other colors allowed.

**Placeholder Sizing**: Placeholders MUST use flexible sizes that adapt to the layout—avoid uniform sizes; each placeholder should be sized appropriately based on its content importance and position in the layout.

Additional Suggestions:
1. Add more texts and examples to serve as supplementary information to make the layout more readable and easy to understand

**Survey Content:**
{content}

**Reference Figures:**
(You have been provided with excellent examples of modern survey visualizations demonstrating current best practices in academic knowledge mapping and field organization.)

**Final Output Requirement:**
A single block of mxGraph XML code (starting with <mxfile> and ending with </mxfile>) that is aesthetically superb and tells a clear, compelling story of the survey's comprehensive knowledge structure and field organization.
"""

def _get_blog_mxgraphxml_prompt_template(content: str, placeholder_spec: str) -> str:
    """Returns the mxGraph XML prompt template for blog posts."""
    return f"""
You are a top-tier educational illustration expert. Please write mxGraph XML code (draw.io format) based on the following blog content to visualize the educational concepts and technical knowledge as clear illustrations.

**CRITICAL FORMAT REQUIREMENTS:**
You MUST output valid mxGraph XML code that follows this exact structure:
```xml
<mxfile>
  <diagram name="Page-1" id="page-1">
    <mxGraphModel dx="1" dy="1" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{CONFIG.get('SVG_WIDTH', 1333)}" pageHeight="{CONFIG.get('SVG_HEIGHT', 750)}" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <!-- Your diagram elements here -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

**mxCell Element Rules:**
- All elements are mxCell tags as DIRECT children of <root>
- Every mxCell (except id="0") MUST have a `parent` attribute
- Shapes: `<mxCell value="label" style="..." vertex="1" parent="1"><mxGeometry x="..." y="..." width="..." height="..." as="geometry"/></mxCell>`
- Edges: `<mxCell edge="1" parent="1" source="sourceId" target="targetId"><mxGeometry relative="1" as="geometry"/></mxCell>`
- Use unique `id` attributes for each mxCell

{_get_mxgraphxml_placeholder_spec()}

**Color Restriction**: The diagram MUST only use black, white, and gray colors—no other colors allowed.

**Placeholder Sizing**: Placeholders MUST use flexible sizes that adapt to the layout—avoid uniform sizes; each placeholder should be sized appropriately based on its content importance and position in the layout.

Additional Suggestions:
1. Add more details (e.g., some examples) to better explain the blog's content.
2. Make the layout orderly and avoid components overlapping (especially lines).

**Blog Content:**
{content}

**Reference Figures:**
(You have been provided with reference blog illustrations showing how to explain technical concepts visually.)

**Final Output Requirement:**
A single block of mxGraph XML code (starting with <mxfile> and ending with </mxfile>) that is aesthetically superb and tells a clear, compelling story of the blog's educational concepts and technical knowledge.
"""

def _get_textbook_mxgraphxml_prompt_template(content: str, placeholder_spec: str) -> str:
    """Returns the mxGraph XML prompt template for textbook content."""
    return f"""
You are a top-tier educational visualization designer. Please write mxGraph XML code (draw.io format) based on the following textbook content to visualize the pedagogical concepts and knowledge structure as clear illustrations.

**CRITICAL FORMAT REQUIREMENTS:**
You MUST output valid mxGraph XML code that follows this exact structure:
```xml
<mxfile>
  <diagram name="Page-1" id="page-1">
    <mxGraphModel dx="1" dy="1" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{CONFIG.get('SVG_WIDTH', 1333)}" pageHeight="{CONFIG.get('SVG_HEIGHT', 750)}" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <!-- Your diagram elements here -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

**mxCell Element Rules:**
- All elements are mxCell tags as DIRECT children of <root>
- Every mxCell (except id="0") MUST have a `parent` attribute
- Shapes: `<mxCell value="label" style="..." vertex="1" parent="1"><mxGeometry x="..." y="..." width="..." height="..." as="geometry"/></mxCell>`
- Edges: `<mxCell edge="1" parent="1" source="sourceId" target="targetId"><mxGeometry relative="1" as="geometry"/></mxCell>`
- Use unique `id` attributes for each mxCell

{_get_mxgraphxml_placeholder_spec()}

**Color Restriction**: The diagram MUST only use black, white, and gray colors—no other colors allowed.

**Placeholder Sizing**: Placeholders MUST use flexible sizes that adapt to the layout—avoid uniform sizes; each placeholder should be sized appropriately based on its content importance and position in the layout.

Additional Suggestions:
1. Add more details (e.g., some examples) to better explain the textbook's content.
2. Make the layout orderly and avoid components overlapping (especially lines).

**Textbook Content:**
{content}

**Reference Figures:**
(You have been provided with reference images to inspire the design.)

**Final Output Requirement:**
A single block of mxGraph XML code (starting with <mxfile> and ending with </mxfile>) that is aesthetically superb and tells a clear, compelling story of the textbook's pedagogical concepts and knowledge structure.
"""


def generate_initial_code(paper_content: str, reference_figures: List[Image.Image], topic: str = 'paper', output_format: str = None) -> Optional[str]:
    """
    Generates initial diagram code (SVG or mxGraph XML) based on the output format.

    Args:
        paper_content: The content to visualize.
        reference_figures: Reference images for design inspiration.
        topic: Content type ('paper', 'survey', 'blog', 'textbook').
        output_format: 'svg' or 'mxgraphxml'. If None, uses CONFIG['OUTPUT_FORMAT'].

    Returns:
        The generated code, or None on failure.
    """
    output_format = output_format or CONFIG.get('OUTPUT_FORMAT', 'svg')
    format_name = 'mxGraph XML' if output_format == 'mxgraphxml' else 'SVG'

    prompt = get_initial_prompt_template(topic, paper_content, output_format)
    try:
        print(f"Generating initial {format_name} figure for {topic.upper()}, learning from references...")

        multimodal_content = [prompt]
        for i, ref_fig in enumerate(reference_figures):
            multimodal_content.extend([
                f"Reference Figure Example {i+1}:",
                ref_fig
            ])

        response = call_google_genai_multimodal(multimodal_content)

        if response is None:
            raise Exception("LLM returned an empty response")

        # Extract code based on format
        if output_format == 'mxgraphxml':
            code_start = response.find('<mxfile')
            code_end = response.rfind('</mxfile>') + 9
            end_offset = 9
        else:
            code_start = response.find('<svg')
            code_end = response.rfind('</svg>') + 6
            end_offset = 6

        if code_start == -1 or code_end == (end_offset - 1):
            raise Exception(f"No valid {format_name} code found in the response")

        code = response[code_start:code_end]

        print(f"Successfully generated initial {format_name} code: {len(code)} characters")

        # Validate and repair if necessary
        is_valid, error_msg = validate_code_syntax(code, output_format)
        if not is_valid:
            print(f"Generated {format_name} has syntax issues: {error_msg}")
            print("Attempting to fix syntax issues...")
            repaired_code = repair_code(code, error_msg, output_format)
            if repaired_code:
                code = repaired_code
                print(f"{format_name} syntax repaired successfully")
            else:
                print(f"{format_name} syntax repair failed, continuing with original code")
        else:
            print(f"{format_name} syntax validation passed")

        return code

    except Exception as e:
        error_msg = str(e)
        print(f"Failed to generate initial {format_name}: {error_msg}")
        # Re-raise with context so the caller can get meaningful error message
        raise Exception(f"Failed to generate initial {format_name}: {error_msg}")

def repair_json(broken_json: str, error_message: str) -> Optional[Dict]:
    """
    Attempts to repair a broken JSON string.
    
    Args:
        broken_json: The broken JSON text.
        error_message: The error message from parsing.
        
    Returns:
        A repaired JSON dictionary, or None on failure.
    """
    prompt = f"""
You are a JSON syntax repair expert. The following text was intended to be a JSON object, but it has syntax errors. Please fix it.

**Error message:**
{error_message}

**Broken JSON text:**
```
{broken_json}
```

**Instructions:**
1.  Analyze the error and the text to locate the syntax issue.
2.  Correct the syntax. Common issues are missing quotes, unescaped characters, or trailing commas.
3.  Return **ONLY** the corrected, valid JSON object, without any additional explanations or surrounding text.
"""
    for attempt in range(CONFIG['MAX_REPAIR_RETRIES']):
        print(f"Attempting to repair JSON (Attempt {attempt + 1}/{CONFIG['MAX_REPAIR_RETRIES']})...")
        try:
            response = call_google_genai_multimodal([prompt])
            if response is None:
                continue
            
            fixed_json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not fixed_json_match:
                continue

            fixed_json_str = fixed_json_match.group(0)
            return json.loads(fixed_json_str)

        except json.JSONDecodeError as e:
            error_message = str(e)
            print(f"Repaired JSON is still invalid: {error_message}")
        except Exception as e:
            print(f"Error calling LLM for JSON repair: {e}")
            
    print("Reached max retries, JSON repair failed.")
    return None

def repair_svg(svg_code: str, error_message: str) -> Optional[str]:
    """
    Attempts to repair broken SVG code.
    
    Args:
        svg_code: The broken SVG code.
        error_message: The parsing error message.
    
    Returns:
        The repaired SVG code, or None after multiple attempts.
    """
    prompt = f"""
You are a professional SVG code debugging expert. The following SVG code has an error during parsing. Please fix it.

**Error Message:**
{error_message}

**Broken SVG Code:**
```xml
{svg_code}
```

**Requirements:**
1.  Carefully analyze the error message and the code to locate the issue.
2.  Fix syntax errors, such as unclosed tags, unescaped special characters, incorrect attributes, etc.
3.  Ensure the repaired code is well-formed XML.
4.  Do not change the visual content of the SVG; only perform syntax repairs.
5.  **Please output the complete, repaired SVG code directly, without any other explanation.**

**Strict Syntax Check:**
- All attribute values must be enclosed in double quotes.
- All tags must be properly closed; self-closing tags should end with "/>".
- Special characters must be escaped: & -> &amp;, < -> &lt;, > -> &gt;.
- Ensure tags are nested correctly with no syntax errors.
- Use only the basic SVG namespace: xmlns="http://www.w3.org/2000/svg"
- Avoid additional namespace declarations like xmlns:xlink or xmlns:xml
- Output format must be strictly: <svg>...</svg>
"""
    
    for attempt in range(CONFIG['MAX_REPAIR_RETRIES']):
        print(f"Attempting to repair SVG (Attempt {attempt + 1}/{CONFIG['MAX_REPAIR_RETRIES']})...")
        try:
            repaired_code = call_google_genai_multimodal([prompt])
            
            if repaired_code is None:
                print("LLM returned an empty response, repair failed.")
                continue

            svg_start = repaired_code.find('<svg')
            svg_end = repaired_code.rfind('</svg>') + 6
            if svg_start == -1 or svg_end == 5:
                 print("No valid SVG code found in the repaired response.")
                 continue
            
            repaired_svg = repaired_code[svg_start:svg_end]

            try:
                processed_repaired_svg = preprocess_svg_for_cairo(repaired_svg)
                cairosvg.svg2png(bytestring=processed_repaired_svg.encode('utf-8'))
                print("SVG code repaired and validated successfully!")
                return processed_repaired_svg
            except Exception as e:
                print(f"Repaired SVG code is still invalid: {e}")
                prompt = prompt.replace(f"**Error Message:**\n{error_message}", f"**Previous repair failed, new error message:**\n{e}")

        except Exception as e:
            print(f"Error calling LLM for repair: {e}")
    
    print("Reached max retries, SVG repair failed.")
    return None


def repair_mxgraphxml(mxgraph_code: str, error_message: str) -> Optional[str]:
    """
    Attempts to repair broken mxGraph XML code.

    Args:
        mxgraph_code: The broken mxGraph XML code.
        error_message: The parsing error message.

    Returns:
        The repaired mxGraph XML code, or None after multiple attempts.
    """
    prompt = f"""
You are a professional mxGraph XML (draw.io format) debugging expert. The following mxGraph XML code has an error during parsing. Please fix it.

**Error Message:**
{error_message}

**Broken mxGraph XML Code:**
```xml
{mxgraph_code}
```

**Requirements:**
1.  Carefully analyze the error message and the code to locate the issue.
2.  Fix syntax errors, such as unclosed tags, unescaped special characters, incorrect attributes, etc.
3.  Ensure the repaired code is well-formed XML.
4.  Do not change the visual content of the diagram; only perform syntax repairs.
5.  **Please output the complete, repaired mxGraph XML code directly, without any other explanation.**

**Strict mxGraph XML Structure Requirements:**
- The code must start with <mxfile> and end with </mxfile>
- Must contain: mxfile > diagram > mxGraphModel > root
- All attribute values must be enclosed in double quotes.
- All tags must be properly closed; self-closing tags should end with "/>".
- Special characters must be escaped: & -> &amp;, < -> &lt;, > -> &gt;.
- All mxCell elements must be DIRECT children of <root>
- mxCell with id="0" must exist (root cell)
- mxCell with id="1" must exist with parent="0" (default parent)
- All other mxCells must have a 'parent' attribute
- Output format must be strictly: <mxfile>...</mxfile>
"""

    for attempt in range(CONFIG['MAX_REPAIR_RETRIES']):
        print(f"Attempting to repair mxGraph XML (Attempt {attempt + 1}/{CONFIG['MAX_REPAIR_RETRIES']})...")
        try:
            repaired_code = call_google_genai_multimodal([prompt])

            if repaired_code is None:
                print("LLM returned an empty response, repair failed.")
                continue

            mxfile_start = repaired_code.find('<mxfile')
            mxfile_end = repaired_code.rfind('</mxfile>') + 9
            if mxfile_start == -1 or mxfile_end == 8:
                print("No valid mxGraph XML code found in the repaired response.")
                continue

            repaired_mxgraph = repaired_code[mxfile_start:mxfile_end]

            # Validate the repaired code
            is_valid, validation_msg = validate_mxgraphxml_syntax(repaired_mxgraph)
            if is_valid:
                print("mxGraph XML code repaired and validated successfully!")
                return repaired_mxgraph
            else:
                print(f"Repaired mxGraph XML is still invalid: {validation_msg}")
                prompt = prompt.replace(f"**Error Message:**\n{error_message}", f"**Previous repair failed, new error message:**\n{validation_msg}")

        except Exception as e:
            print(f"Error calling LLM for repair: {e}")

    print("Reached max retries, mxGraph XML repair failed.")
    return None


def repair_code(code: str, error_message: str, output_format: str = None) -> Optional[str]:
    """
    Attempts to repair broken code based on output format.

    Args:
        code: The broken code (SVG or mxGraph XML).
        error_message: The parsing error message.
        output_format: 'svg' or 'mxgraphxml'. If None, uses CONFIG['OUTPUT_FORMAT'].

    Returns:
        The repaired code, or None after multiple attempts.
    """
    output_format = output_format or CONFIG.get('OUTPUT_FORMAT', 'svg')

    if output_format == 'mxgraphxml':
        return repair_mxgraphxml(code, error_message)
    else:
        return repair_svg(code, error_message)


def validate_svg_syntax(svg_code: str) -> Tuple[bool, str]:
    try:
        import xml.etree.ElementTree as ET

        if not svg_code.strip().startswith('<svg'):
            return False, "SVG code must start with <svg"

        if not svg_code.strip().endswith('</svg>'):
            return False, "SVG code must end with </svg>"

        try:
            ET.fromstring(svg_code)
        except ET.ParseError as e:
            return False, f"XML parsing error: {e}"

        lines = svg_code.split('\n')
        for i, line in enumerate(lines, 1):
            import re
            unquoted_attrs = re.findall(r'(\w+)=([^"\s>]+)', line)
            if unquoted_attrs:
                return False, f"Line {i} has unquoted attribute values: {unquoted_attrs[0]}"

        return True, "SVG syntax is correct"

    except Exception as e:
        return False, f"Validation process error: {e}"


def validate_mxgraphxml_syntax(mxgraph_code: str) -> Tuple[bool, str]:
    """
    Validates mxGraph XML syntax for draw.io compatibility.

    Args:
        mxgraph_code: The mxGraph XML code to validate.

    Returns:
        Tuple of (is_valid, error_message_or_success_message)
    """
    try:
        import xml.etree.ElementTree as ET

        code = mxgraph_code.strip()

        # Check for mxfile wrapper
        if not code.startswith('<mxfile'):
            return False, "mxGraph XML must start with <mxfile>"

        if not code.endswith('</mxfile>'):
            return False, "mxGraph XML must end with </mxfile>"

        # Try to parse as XML
        try:
            root = ET.fromstring(code)
        except ET.ParseError as e:
            return False, f"XML parsing error: {e}"

        # Check for required structure: mxfile > diagram > mxGraphModel > root
        diagram = root.find('.//diagram')
        if diagram is None:
            return False, "Missing <diagram> element inside <mxfile>"

        graph_model = diagram.find('.//mxGraphModel')
        if graph_model is None:
            return False, "Missing <mxGraphModel> element inside <diagram>"

        root_elem = graph_model.find('.//root')
        if root_elem is None:
            return False, "Missing <root> element inside <mxGraphModel>"

        # Check for base mxCells (id="0" and id="1")
        mxcells = root_elem.findall('mxCell')
        cell_ids = [cell.get('id') for cell in mxcells]

        if '0' not in cell_ids:
            return False, "Missing required mxCell with id='0'"

        if '1' not in cell_ids:
            return False, "Missing required mxCell with id='1' (default parent)"

        # Check that all mxCells (except id="0") have parent attribute
        for cell in mxcells:
            cell_id = cell.get('id')
            if cell_id != '0' and cell.get('parent') is None:
                return False, f"mxCell id='{cell_id}' is missing required 'parent' attribute"

        # Check for unquoted attributes in XML tags
        # The approach: extract content outside of quoted strings, then check for unquoted attrs
        lines = code.split('\n')
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                continue

            # Only check lines that contain XML tags
            if '<' not in stripped:
                continue

            # Extract tag content (between < and >)
            tag_matches = re.findall(r'<([^>]+)>', stripped)
            for tag_content in tag_matches:
                # Skip closing tags and special tags
                if tag_content.startswith('/') or tag_content.startswith('?') or tag_content.startswith('!'):
                    continue

                # Remove the tag name to get just attributes
                parts = tag_content.split(None, 1)
                if len(parts) < 2:
                    continue  # No attributes

                attr_string = parts[1].rstrip('/')

                # Parse attributes properly: remove all quoted values first
                # Replace all "..." content with placeholder to avoid false positives
                cleaned = re.sub(r'"[^"]*"', '""', attr_string)

                # Now check for patterns like attr=value where value is not quoted
                # Pattern: word= followed by something that's not a quote or space
                unquoted = re.findall(r'(\w+)=([^"\s][^\s]*)', cleaned)
                # Filter: only report if value doesn't start with quote placeholder
                real_unquoted = [(k, v) for k, v in unquoted if v != '""' and not v.startswith('"')]
                if real_unquoted:
                    return False, f"Line {i} has unquoted attribute values: {real_unquoted[0]}"

        return True, "mxGraph XML syntax is correct"

    except Exception as e:
        return False, f"Validation process error: {e}"


def validate_code_syntax(code: str, output_format: str = None) -> Tuple[bool, str]:
    """
    Validates code syntax based on the output format.

    Args:
        code: The code to validate (SVG or mxGraph XML).
        output_format: 'svg' or 'mxgraphxml'. If None, uses CONFIG['OUTPUT_FORMAT'].

    Returns:
        Tuple of (is_valid, error_message_or_success_message)
    """
    output_format = output_format or CONFIG.get('OUTPUT_FORMAT', 'svg')

    if output_format == 'mxgraphxml':
        return validate_mxgraphxml_syntax(code)
    else:
        return validate_svg_syntax(code)

def preprocess_svg_for_cairo(svg_code: str) -> str:
    import re
    
    svg_code = re.sub(r'\s*xmlns:xlink="[^"]*"', '', svg_code)
    svg_code = re.sub(r'\s*xmlns:xml="[^"]*"', '', svg_code)
    
    if 'xmlns="http://www.w3.org/2000/svg"' not in svg_code:
        svg_code = svg_code.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    
    svg_code = re.sub(r'xmlns="http://www\.w3\.org/2000/svg"\s+xmlns="http://www\.w3\.org/2000/svg"', 
                     'xmlns="http://www.w3.org/2000/svg"', svg_code)
    
    svg_code = re.sub(r'\s{2,}', ' ', svg_code)
    svg_code = svg_code.strip()
    
    return svg_code

def svg_to_png(svg_code: str, output_path: str, attempt_repair: bool = False) -> Tuple[bool, Optional[str]]:
    try:
        processed_svg = preprocess_svg_for_cairo(svg_code)

        cairosvg.svg2png(
            bytestring=processed_svg.encode('utf-8'),
            write_to=output_path,
            output_width=CONFIG['SVG_WIDTH'],
            output_height=CONFIG['SVG_HEIGHT']
        )
        return True, processed_svg

    except Exception as e:
        error_msg = str(e)
        print(f"SVG to PNG conversion failed: {error_msg}")
        if attempt_repair:
            repaired_svg = repair_svg(processed_svg if 'processed_svg' in locals() else svg_code, error_msg)
            if repaired_svg:
                return svg_to_png(repaired_svg, output_path, attempt_repair=False)
        return False, None


def mxgraphxml_to_png(mxgraph_code: str, output_path: str, attempt_repair: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Converts mxGraph XML to PNG using Playwright (headless browser) with draw.io embed.

    This approach mirrors how next-ai-draw-io exports diagrams:
    - Uses https://embed.diagrams.net to render the diagram
    - Exports via the embedded draw.io editor's export functionality

    Args:
        mxgraph_code: The mxGraph XML code.
        output_path: Path to save the PNG file.
        attempt_repair: Whether to attempt repair if validation fails.

    Returns:
        Tuple of (success, processed_code)

    Raises:
        RuntimeError: If conversion fails.
    """
    # Validate the mxGraph XML first
    is_valid, error_msg = validate_mxgraphxml_syntax(mxgraph_code)

    if not is_valid:
        print(f"mxGraph XML validation failed: {error_msg}")
        if attempt_repair:
            repaired_code = repair_mxgraphxml(mxgraph_code, error_msg)
            if repaired_code:
                return mxgraphxml_to_png(repaired_code, output_path, attempt_repair=False)
        raise RuntimeError(f"mxGraph XML validation failed: {error_msg}")

    # Get canvas dimensions from CONFIG
    scale = CONFIG.get('MXGRAPH_EXPORT_SCALE', 2)

    print("Converting mxGraph XML to PNG via Playwright (headless browser)...")

    try:
        png_data = _export_via_playwright(mxgraph_code, scale)
        if png_data:
            with open(output_path, 'wb') as f:
                f.write(png_data)
            print(f"mxGraph XML successfully converted to PNG: {output_path}")
            return True, mxgraph_code
        else:
            raise RuntimeError("Playwright export returned no data")
    except ImportError as e:
        raise RuntimeError(
            f"Playwright not installed. Please install it:\n"
            f"  pip install playwright\n"
            f"  playwright install chromium\n"
            f"Original error: {e}"
        )
    except Exception as e:
        raise RuntimeError(f"Failed to convert mxGraph XML to PNG: {e}")


def _export_via_playwright(mxgraph_code: str, scale: int = 2) -> Optional[bytes]:
    """
    Export mxGraph XML to PNG using Playwright with draw.io embed mode.

    This mirrors the approach used by next-ai-draw-io (react-drawio component).
    The protocol is:
    1. draw.io sends {event: 'init'} when ready
    2. Host sends {action: 'load', xml: '...'} to load diagram
    3. draw.io sends {event: 'load', ...} when loaded
    4. Host sends {action: 'export', format: 'png', ...} to export
    5. draw.io sends {event: 'export', data: '...'} with the PNG data URI

    Args:
        mxgraph_code: The mxGraph XML code.
        scale: Scale factor for the output image.

    Returns:
        PNG image data as bytes, or None if export failed.
    """
    from playwright.sync_api import sync_playwright
    import base64
    import json
    import tempfile

    # Create HTML page that hosts draw.io in an iframe
    # This is how react-drawio works - it embeds draw.io in an iframe and communicates via postMessage
    html_content = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Draw.io Export</title>
    <style>
        body, html { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; }
        iframe { width: 100%; height: 100%; border: none; }
    </style>
</head>
<body>
    <iframe id="drawio" src="https://embed.diagrams.net/?embed=1&proto=json&spin=1"></iframe>
    <script>
        window.exportResult = null;
        window.drawioReady = false;
        window.diagramLoaded = false;

        window.addEventListener('message', function(evt) {
            if (evt.data && typeof evt.data === 'string') {
                try {
                    var msg = JSON.parse(evt.data);
                    console.log('DRAWIO_MSG:' + JSON.stringify(msg));

                    if (msg.event === 'init') {
                        window.drawioReady = true;
                        console.log('DRAWIO_READY');
                    } else if (msg.event === 'load') {
                        window.diagramLoaded = true;
                        console.log('DRAWIO_LOADED');
                    } else if (msg.event === 'export') {
                        window.exportResult = msg.data;
                        console.log('DRAWIO_EXPORTED');
                    }
                } catch(e) {}
            }
        });

        window.sendToDrawio = function(msg) {
            var iframe = document.getElementById('drawio');
            iframe.contentWindow.postMessage(JSON.stringify(msg), '*');
        };
    </script>
</body>
</html>
'''

    png_data = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        # Create temporary HTML file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html_content)
            temp_html_path = f.name

        try:
            # Navigate to our HTML page
            page.goto(f'file://{temp_html_path}', wait_until='networkidle', timeout=60000)

            # Wait for draw.io to be ready (init event)
            print("Waiting for draw.io to initialize...")
            max_wait = 30
            for _ in range(max_wait * 2):
                is_ready = page.evaluate('window.drawioReady')
                if is_ready:
                    break
                page.wait_for_timeout(500)
            else:
                raise RuntimeError("draw.io failed to initialize within 30 seconds")

            print("draw.io initialized, loading diagram...")

            # Escape the XML for JSON embedding
            escaped_xml = mxgraph_code.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')

            # Load the diagram
            page.evaluate(f'''
                window.sendToDrawio({{
                    action: "load",
                    xml: "{escaped_xml}",
                    autosave: 0
                }});
            ''')

            # Wait for diagram to load
            for _ in range(max_wait * 2):
                is_loaded = page.evaluate('window.diagramLoaded')
                if is_loaded:
                    break
                page.wait_for_timeout(500)
            else:
                raise RuntimeError("Diagram failed to load within 30 seconds")

            print("Diagram loaded, exporting to PNG...")

            # Export as PNG
            page.evaluate(f'''
                window.sendToDrawio({{
                    action: "export",
                    format: "png",
                    scale: {scale},
                    border: 10,
                    background: "#ffffff"
                }});
            ''')

            # Wait for export result
            for _ in range(max_wait * 2):
                export_data = page.evaluate('window.exportResult')
                if export_data:
                    break
                page.wait_for_timeout(500)
            else:
                raise RuntimeError("Export failed to complete within 30 seconds")

            print("Export completed, processing data...")

            # Process the export data
            if export_data:
                # Remove data URI prefix if present
                if export_data.startswith('data:image/png;base64,'):
                    export_data = export_data[22:]
                png_data = base64.b64decode(export_data)

        finally:
            browser.close()
            # Clean up temp file
            try:
                os.unlink(temp_html_path)
            except:
                pass

    return png_data


def code_to_png(code: str, output_path: str, attempt_repair: bool = False, output_format: str = None) -> Tuple[bool, Optional[str]]:
    """
    Converts code (SVG or mxGraph XML) to PNG based on output format.

    Args:
        code: The code to convert (SVG or mxGraph XML).
        output_path: Path to save the PNG file.
        attempt_repair: Whether to attempt repair if conversion fails.
        output_format: 'svg' or 'mxgraphxml'. If None, uses CONFIG['OUTPUT_FORMAT'].

    Returns:
        Tuple of (success, processed_code)
    """
    output_format = output_format or CONFIG.get('OUTPUT_FORMAT', 'svg')

    if output_format == 'mxgraphxml':
        return mxgraphxml_to_png(code, output_path, attempt_repair)
    else:
        return svg_to_png(code, output_path, attempt_repair)


def create_fallback_evaluation(default_score: float = 5.0) -> Dict:
    return {
        "scores": {
            "aesthetic_design": default_score,
            "content_fidelity": default_score,
            "placeholder_usage": default_score
        },
        "overall_quality": default_score,
        "critique_summary": "Unable to generate detailed critique due to JSON parsing error. Using default evaluation.",
        "specific_issues": ["JSON parsing failed, unable to provide specific analysis"],
        "improvement_suggestions": ["Please check LLM response format"]
    }


def extract_json_robustly(response_text: str) -> Optional[Dict]:
    if not response_text:
        return None
    
    try:
        return json.loads(response_text.strip())
    except json.JSONDecodeError:
        pass
    
    import re
    json_code_blocks = re.findall(r'```(?:json)?\s*\n(.*?)\n```', response_text, re.DOTALL | re.IGNORECASE)
    for block in json_code_blocks:
        try:
            return json.loads(block.strip())
        except json.JSONDecodeError:
            continue

    json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    json_matches = re.findall(json_pattern, response_text, re.DOTALL)
    for match in json_matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue

    def find_json_bounds(text, start_pos=0):
        start = text.find('{', start_pos)
        if start == -1:
            return None, None
        
        bracket_count = 0
        in_string = False
        escape_next = False
        
        for i in range(start, len(text)):
            char = text[i]
            
            if escape_next:
                escape_next = False
                continue
                
            if char == '\\':
                escape_next = True
                continue
                
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
                
            if not in_string:
                if char == '{':
                    bracket_count += 1
                elif char == '}':
                    bracket_count -= 1
                    if bracket_count == 0:
                        return start, i + 1
        
        return None, None
    
    start, end = find_json_bounds(response_text)
    if start is not None and end is not None:
        try:
            return json.loads(response_text[start:end])
        except json.JSONDecodeError:
            pass
    
    print(f"Unable to extract valid JSON from response: {response_text}")
    return None


def evaluate_code(
    code: str,
    code_image: Image.Image,
    paper_content: str,
    reference_figures: List[Image.Image],
    iteration: int,
    topic: str = 'paper',
    output_format: str = None
) -> Tuple[float, Optional[Dict]]:
    """
    Evaluation Agent: Evaluate code (SVG or mxGraph XML) quality, return score and critique
    Supports all topic types: paper, survey, blog, textbook
    Supports all output formats: svg, mxgraphxml
    """
    output_format = output_format or CONFIG.get('OUTPUT_FORMAT', 'svg')
    format_name = 'mxGraph XML' if output_format == 'mxgraphxml' else 'SVG'

    # Build evaluation prompt based on topic type
    topic_descriptors = {
        'paper': 'research paper methodology visualization',
        'survey': 'survey knowledge structure and field organization',
        'blog': 'blog educational concepts and technical knowledge',
        'textbook': 'textbook pedagogical concepts and knowledge structure'
    }

    topic_desc = topic_descriptors.get(topic, 'content visualization')
    content_label = topic.title() + ' Content'

    # Add color restriction and placeholder sizing for mxgraphxml
    mxgraphxml_requirements = """**Color Restriction**: The diagram MUST only use black, white, and gray colors—no other colors allowed.

**Placeholder Sizing**: Placeholders MUST use flexible sizes that adapt to the layout—avoid uniform sizes; each placeholder should be sized appropriately based on its content importance and position in the layout.

""" if output_format == 'mxgraphxml' else ""

    evaluation_prompt = f"""
You are a STRICT and CRITICAL figure evaluator. Your task is to rigorously evaluate the {format_name} layout for {topic_desc}. Be harsh—do NOT inflate scores.

{mxgraphxml_requirements}**Strict Scoring Criteria (0-10):**

1. **Aesthetic Design** (most figures score 4-6):
   - 9-10: Publication-ready, flawless
   - 7-8: Good with minor issues
   - 5-6: Acceptable but mediocre (some overlaps, spacing issues)
   - 3-4: Poor (cluttered, misaligned, overlapping)
   - 0-2: Broken/unreadable
   Deduct: -2 per overlap, -1 per alignment issue, -2 for color violations

2. **Content Fidelity** (most figures score 5-7):
   - 9-10: Captures ALL key concepts perfectly
   - 7-8: Most content with minor omissions
   - 5-6: Basic concepts but missing details
   - 3-4: Significant content missing
   - 0-2: Fails to represent content
   Deduct: -2 per missing key concept, -1 per incorrect relationship

3. **Placeholder Usage** (most figures score 3-6):
   - 9-10: All placeholders have exterior labels AND interior [icon] descriptions
   - 7-8: Most correct with minor issues
   - 5-6: Placeholders present but missing labels/descriptions
   - 3-4: Few proper placeholders
   - 0-2: No proper placeholders
   Deduct: -1 per missing label, -1 per missing [icon] description

**Current Layout (Iteration {iteration}):**
[PNG image and {format_name} code provided below]

**{content_label}:**
{paper_content}

**Output (JSON only, be STRICT):**
{{
    "scores": {{
        "aesthetic_design": <0-10>,
        "content_fidelity": <0-10>,
        "placeholder_usage": <0-10>
    }},
    "overall_quality": <average>,
    "critique_summary": "<strengths_and_weaknesses>",
    "specific_issues": ["<issue1>", ...],
    "improvement_suggestions": ["<suggestion1>", ...]
}}
"""

    try:
        print(f"[Evaluation Agent] Evaluating iteration {iteration} {topic.upper()} {format_name} quality...")

        multimodal_content = [
            evaluation_prompt,
            f"Current figure (PNG for visual reference):",
            code_image,
            f"Current {format_name} code (text for structural analysis):",
            code
        ]

        for i, ref_fig in enumerate(reference_figures):
            multimodal_content.extend([
                f"Reference figure example {i+1}:",
                ref_fig
            ])

        response = call_google_genai_multimodal(multimodal_content)

        if response is None:
            raise Exception("LLM returned an empty response")

        critique_result = extract_json_robustly(response)
        if critique_result is None:
            print(f"[Evaluation Agent] JSON parsing failed, using default score")
            critique_result = create_fallback_evaluation(5.0)

        overall_quality = critique_result.get('overall_quality', 5.0)

        print(f"[Evaluation Agent] Evaluation result: {overall_quality:.1f}/10")
        if 'scores' in critique_result and isinstance(critique_result.get('scores'), dict):
            for dim, score in critique_result['scores'].items():
                print(f"   {dim}: {score}/10")

        return overall_quality, critique_result

    except Exception as e:
        print(f"[Evaluation Agent] Evaluation failed: {e}")
        return 5.0, create_fallback_evaluation(5.0)


def improve_code(
    code: str,
    code_image: Image.Image,
    paper_content: str,
    reference_figures: List[Image.Image],
    iteration: int,
    previous_critique: Optional[Dict],
    human_guidance: Optional[str] = None,
    topic: str = 'paper',
    output_format: str = None
) -> Optional[str]:
    """
    Improvement Agent: Generate improved code (SVG or mxGraph XML) based on previous critique
    Use initial generation prompt + previous evaluation result to guide improvement
    """
    output_format = output_format or CONFIG.get('OUTPUT_FORMAT', 'svg')
    format_name = 'mxGraph XML' if output_format == 'mxgraphxml' else 'SVG'

    # Determine code extraction patterns based on format
    if output_format == 'mxgraphxml':
        start_tag = '<mxfile'
        end_tag = '</mxfile>'
        end_offset = 9
    else:
        start_tag = '<svg'
        end_tag = '</svg>'
        end_offset = 6

    try:
        # Get initial generation prompt as base
        base_prompt = get_initial_prompt_template(topic, paper_content, output_format)

        # Add previous evaluation feedback on top of initial prompt
        improvement_prompt = base_prompt

        # Add previous evaluation result as improvement guidance
        if previous_critique:
            try:
                previous_eval_json_str = json.dumps(previous_critique, ensure_ascii=False, indent=2)
                improvement_prompt += f"""

**Previous Iteration Evaluation (Iteration {iteration-1}):**
The previous design received the following evaluation:

{previous_eval_json_str}

**CRITICAL IMPROVEMENT REQUIREMENTS:**
1. You MUST systematically address each item in 'specific_issues'
2. You MUST implement each item in 'improvement_suggestions'
3. Focus especially on fixing:
   - Component overlap and alignment issues
   - Connector correctness and clarity
   - Layout balance and aesthetic quality
   - Content accuracy and completeness
   - Placeholder compliance
"""
            except Exception as e:
                print(f"[Improvement Agent] Cannot format previous_critique: {e}")

        # Add human guidance (if any)
        if human_guidance:
            improvement_prompt += f"""

**Additional Human Guidance:**
{human_guidance}
"""

        # Emphasize output format
        if output_format == 'mxgraphxml':
            improvement_prompt += """

**Color Restriction**: The diagram MUST only use black, white, and gray colors—no other colors allowed.

**Placeholder Sizing**: Placeholders MUST use flexible sizes that adapt to the layout—avoid uniform sizes; each placeholder should be sized appropriately based on its content importance and position in the layout.

**IMPORTANT OUTPUT INSTRUCTION:**
Output ONLY the complete, improved mxGraph XML code.
Start directly with <mxfile> tag and end with </mxfile> tag.
Do NOT output any explanatory text or JSON.
"""
        else:
            improvement_prompt += """

**IMPORTANT OUTPUT INSTRUCTION:**
Output ONLY the complete, improved SVG code.
Start directly with <svg> tag and end with </svg> tag.
Do NOT output any explanatory text or JSON.
"""

        print(f"[Improvement Agent] Generating improved {iteration-1} based on iteration{topic.upper()} {format_name}...", flush=True)
        print(f"[Improvement Agent] Input code length: {len(code)}", flush=True)
        print(f"[Improvement Agent] LLM Provider: {CONFIG.get('LLM_PROVIDER')}", flush=True)

        multimodal_content = [
            improvement_prompt,
            f"Previous iteration's figure (Iteration {iteration-1} - for reference):",
            code_image,
            f"Previous iteration's {format_name} code (Iteration {iteration-1} - to improve upon):",
            code
        ]

        for i, ref_fig in enumerate(reference_figures):
            multimodal_content.extend([
                f"Reference figure example {i+1}:",
                ref_fig
            ])

        print(f"[Improvement Agent] Calling LLM...", flush=True)
        response = call_google_genai_multimodal(multimodal_content)
        print(f"[Improvement Agent] LLM response length: {len(response) if response else 0}", flush=True)

        if response is None:
            raise Exception("LLM returned an empty response")

        # Robust code extraction - handle markdown code blocks and direct XML
        improved_code = None

        # Method 1: Try direct extraction (XML without markdown)
        code_start = response.find(start_tag)
        if code_start != -1:
            code_end = response.rfind(end_tag)
            if code_end != -1:
                code_end += len(end_tag)
                improved_code = response[code_start:code_end].strip()
                print(f"[Improvement Agent] Direct extraction successful: start={code_start}, end={code_end}", flush=True)

        # Method 2: Try extracting from markdown code blocks
        if not improved_code:
            import re
            # Match various markdown code block formats
            code_block_patterns = [
                r'```(?:xml|mxgraph|mxfile|drawio)?\s*\n(.*?)```',  # Standard markdown
                r'```\s*(.*?)```',  # Generic code block
            ]
            for pattern in code_block_patterns:
                matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
                for match in matches:
                    if start_tag in match:
                        inner_start = match.find(start_tag)
                        inner_end = match.rfind(end_tag)
                        if inner_start != -1 and inner_end != -1:
                            improved_code = match[inner_start:inner_end + len(end_tag)].strip()
                            print(f"[Improvement Agent] Markdown extraction successful", flush=True)
                            break
                if improved_code:
                    break

        if not improved_code:
            print(f"[Improvement Agent] No valid{format_name} code found in response", flush=True)
            print(f"[Improvement Agent] Response first 500 chars: {response[:500] if response else 'NONE'}", flush=True)
            print(f"[Improvement Agent] Response last 500 chars: {response[-500:] if response and len(response) > 500 else response}", flush=True)
            return None

        # Validate syntax
        is_valid, error_msg = validate_code_syntax(improved_code, output_format)
        if not is_valid:
            print(f"[Improvement Agent] Generated{format_name} has syntax issues: {error_msg}")
            print("[Improvement Agent] Attempting to fix syntax issues...")
            repaired_code = repair_code(improved_code, error_msg, output_format)
            if repaired_code:
                improved_code = repaired_code
                print(f"[Improvement Agent] {format_name} syntax fix successful")
            else:
                print(f"[Improvement Agent] {format_name} syntax fix failed")
                return None
        else:
            print(f"[Improvement Agent] {format_name} syntax validation passed")

        return improved_code

    except Exception as e:
        print(f"[Improvement Agent] Improvement failed: {e}")
        return None


def save_iteration_results(
    iteration: int,
    code: str,
    quality_score: float,
    output_dir: str,
    human_quality_score: Optional[float] = None,
    human_guidance: Optional[str] = None,
    evaluation_data: Optional[Dict] = None,
    output_format: str = None
) -> Optional[str]:
    """
    Save iteration results to files.

    Args:
        iteration: The iteration number.
        code: The SVG or mxGraph XML code to save.
        quality_score: The quality score for this iteration.
        output_dir: Directory to save results.
        human_quality_score: Optional human-provided quality score.
        human_guidance: Optional human guidance for improvement.
        evaluation_data: Optional evaluation data dictionary.
        output_format: 'svg' or 'mxgraphxml'. If None, uses CONFIG['OUTPUT_FORMAT'].

    Returns:
        The final code (possibly repaired), or None if save failed.
    """
    output_format = output_format or CONFIG.get('OUTPUT_FORMAT', 'svg')
    format_name = 'mxGraph XML' if output_format == 'mxgraphxml' else 'SVG'
    file_ext = '.drawio' if output_format == 'mxgraphxml' else '.svg'

    try:
        code_path = os.path.join(output_dir, f'iteration_{iteration}{file_ext}')
        with open(code_path, 'w', encoding='utf-8') as f:
            f.write(code)

        png_path = os.path.join(output_dir, f'iteration_{iteration}.png')
        success, final_code = code_to_png(code, png_path, attempt_repair=True, output_format=output_format)

        score_record = {
            'iteration': iteration,
            'quality_score': quality_score,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'output_format': output_format,
            'code_repaired': code != final_code,
            'evaluation_data': evaluation_data or {},
            'human_feedback': {
                'human_quality_score': human_quality_score,
                'human_guidance': human_guidance
            }
        }

        score_path = os.path.join(output_dir, f'iteration_{iteration}_evaluation.json')
        with open(score_path, 'w', encoding='utf-8') as f:
            json.dump(score_record, f, indent=2, ensure_ascii=False)

        if success:
            if code != final_code:
                repaired_code_path = os.path.join(output_dir, f'iteration_{iteration}{file_ext}')
                with open(repaired_code_path, 'w', encoding='utf-8') as f:
                    f.write(final_code)
                print(f"Original {format_name} was invalid, but it has been successfully repaired and saved.")

            print(f"Iteration {iteration} results saved (Quality Score: {quality_score:.1f})")
            return final_code
        else:
            print(f"{format_name} code for iteration {iteration} is invalid and could not be repaired, skipping save.")
            return None

    except Exception as e:
        print(f"An unexpected error occurred while saving iteration {iteration} results: {e}")
        return None

def figure_generator_pipeline(
    paper_path: str = "paper.md",
    reference_figures: List[str] = None,
    topic: str = 'paper',
    output_format: str = None
) -> Dict[str, Any]:
    """
    Main pipeline for generating scientific figures (SVG or mxGraph XML format).

    Args:
        paper_path: Path to the content file.
        reference_figures: List of reference figure paths.
        topic: Content type ('paper', 'survey', 'blog', 'textbook').
        output_format: 'svg' or 'mxgraphxml'. If None, uses CONFIG['OUTPUT_FORMAT'].

    Returns:
        Dictionary with generation results and file paths.
    """
    output_format = output_format or CONFIG.get('OUTPUT_FORMAT', 'svg')
    format_name = 'mxGraph XML' if output_format == 'mxgraphxml' else 'SVG'
    file_ext = '.drawio' if output_format == 'mxgraphxml' else '.svg'

    if topic not in CONFIG['SUPPORTED_TOPICS']:
        return {"error": f"Unsupported topic: {topic}. Supported topics are: {CONFIG['SUPPORTED_TOPICS']}"}

    output_dir = CONFIG['OUTPUT_DIR']
    os.makedirs(output_dir, exist_ok=True)

    print(f"\nStep 1: Reading {topic} content")
    paper_content = read_paper_content(paper_path)
    if not paper_content:
        return {"error": "Could not read paper content"}

    print("\nStep 2: Loading reference figures")
    ref_figures = load_reference_figures(reference_figures)
    if not ref_figures:
        print("Failed to load reference figures, will generate based on paper content only.")

    print(f"\nStep 3: Generating initial {format_name} code")
    current_code = generate_initial_code(paper_content, ref_figures, topic, output_format)
    if not current_code:
        return {"error": f"Could not generate initial {format_name} code"}

    initial_png_path = os.path.join(output_dir, 'initial_figure.png')
    success, repaired_code = code_to_png(current_code, initial_png_path, attempt_repair=True, output_format=output_format)

    if not success:
        error_message = f"Initial {format_name} code is invalid and could not be auto-repaired. Terminating process."
        print(f"{error_message}")
        broken_code_path = os.path.join(output_dir, f'broken_initial{file_ext}')
        with open(broken_code_path, 'w', encoding='utf-8') as f:
            f.write(current_code)
        return {"error": error_message, "broken_code_path": broken_code_path}

    print(f"\nEvaluating initial{format_name} quality...")
    initial_png_image = Image.open(initial_png_path)
    initial_quality_score, initial_critique = evaluate_code(
        repaired_code, initial_png_image, paper_content, ref_figures, 0, topic=topic, output_format=output_format
    )

    if initial_quality_score is None or initial_quality_score <= 0:
        print(f"Initial {format_name} evaluation failed, using default score5.0")
        initial_quality_score = 5.0
    else:
        print(f"Initial {format_name} score: {initial_quality_score:.1f}/10")

    human_guidance = None
    human_quality_score = None
    if CONFIG.get('HUMAN_IN_LOOP', False):
        try:
            if CONFIG.get('AUTO_OPEN_IMAGES', True):
                try:
                    os.startfile(initial_png_path)
                except Exception:
                    webbrowser.open(f"file://{os.path.abspath(initial_png_path)}", new=2)
            print("Human review: Please check the current layout in the opened image.")
            print("Please enter score for current figure (0-10, press Enter to skip): ", end="")
            user_score_input = input().strip()
            if user_score_input:
                try:
                    human_quality_score = float(user_score_input)
                except ValueError:
                    human_quality_score = None
            print("Please enter improvement suggestions (press Enter to finish, leave empty to skip):")
            human_guidance = input().strip() or None
        except Exception as e:
            print(f"Unable to collect human feedback：{e}")

    if CONFIG.get('HUMAN_IN_LOOP', False):
        effective_initial_score = human_quality_score if isinstance(human_quality_score, (int, float)) else initial_quality_score
    else:
        effective_initial_score = initial_quality_score

    saved_code = save_iteration_results(0, repaired_code, effective_initial_score, output_dir, human_quality_score, human_guidance, evaluation_data=initial_critique, output_format=output_format)
    if saved_code is None:
         return {"error": f"Initial {format_name} was invalid and could not be repaired. Terminated."}

    print("\nStep 4: Starting iterative optimization loop")
    print(f"Max iterations: {CONFIG['MAX_ITERATIONS']}")
    print(f"Quality threshold: {CONFIG['QUALITY_THRESHOLD']}/10")

    best_code = saved_code
    best_score = effective_initial_score
    best_iteration_num = 0
    iteration_history = [{'iteration': 0, 'quality_score': effective_initial_score, 'improvement': 0, 'critique': initial_critique, 'human_quality_score': human_quality_score, 'human_guidance': human_guidance}]

    for iteration in range(1, CONFIG['MAX_ITERATIONS'] + 1):
        print(f"\n--- Iteration {iteration} ---")
        print(f"Current best result from iteration {best_iteration_num} (Score: {best_score:.1f})")

        # Get previous (or best) iteration code, image and critique
        previous_iteration_num = iteration - 1
        previous_code_path = os.path.join(output_dir, f'iteration_{previous_iteration_num}{file_ext}')
        previous_png_path = os.path.join(output_dir, f'iteration_{previous_iteration_num}.png')

        try:
            with open(previous_code_path, 'r', encoding='utf-8') as f:
                previous_code = f.read()
            previous_png_image = Image.open(previous_png_path)
        except Exception as e:
            print(f"Unable to load iteration {previous_iteration_num} files: {e}. . Terminating process.")
            break

        # Get previous iteration critique
        previous_critique = None
        if iteration_history:
            last_record = iteration_history[-1]
            previous_critique = last_record.get('critique')

        # ====== Step 1: Improvement Agent - Generate new code based on previous critique ======
        print(f"\n[Step 1/2] Improvement Agent working...")
        improved_code = improve_code(
            previous_code,
            previous_png_image,
            paper_content,
            ref_figures,
            iteration,
            previous_critique,
            human_guidance=human_guidance,
            topic=topic,
            output_format=output_format
        )

        if improved_code is None:
            print(f"Iteration {iteration}  improvement failed, unable to generate valid{format_name}。. Skipping this iteration.")
            iteration_history.append({
                'iteration': iteration,
                'quality_score': None,
                'improvement': 0,
                'critique': None
            })
            continue

        # ====== Step 2: Evaluation Agent - Evaluate newly generated code ======
        print(f"\n[Step 2/2] Evaluation Agent working...")

        # First convert to PNG for evaluation
        temp_png_path = os.path.join(output_dir, f'temp_iteration_{iteration}.png')
        temp_conversion_success, _ = code_to_png(improved_code, temp_png_path, attempt_repair=False, output_format=output_format)

        if not temp_conversion_success:
            print(f"Iteration {iteration}  {format_name}cannot convert to PNG,. Skipping this iteration.")
            iteration_history.append({
                'iteration': iteration,
                'quality_score': None,
                'improvement': 0,
                'critique': None
            })
            continue

        try:
            temp_png_image = Image.open(temp_png_path)
            quality_score, critique_result = evaluate_code(
                improved_code,
                temp_png_image,
                paper_content,
                ref_figures,
                iteration,
                topic=topic,
                output_format=output_format
            )
            
            # Clean up temporary files
            if os.path.exists(temp_png_path):
                os.remove(temp_png_path)
            
            print(f"\n[Evaluation Complete] Iteration {iteration}  score: {quality_score:.1f}/10")
            
        except Exception as e:
            print(f"Iteration {iteration}  evaluation error: {e}, skipping this iteration")
            if os.path.exists(temp_png_path):
                os.remove(temp_png_path)
            iteration_history.append({
                'iteration': iteration,
                'quality_score': None, 
                'improvement': 0,
                'critique': None
            })
            continue

        # ====== Human feedback (if enabled)======
        human_quality_score = None
        human_guidance_next = None
        if CONFIG.get('HUMAN_IN_LOOP', False):
            # Save current iteration result for human review
            temp_save_path = os.path.join(output_dir, f'temp_iteration_{iteration}_preview.png')
            code_to_png(improved_code, temp_save_path, attempt_repair=False, output_format=output_format)

            try:
                if os.path.exists(temp_save_path):
                    try:
                        os.startfile(temp_save_path)
                    except Exception:
                        webbrowser.open(f"file://{os.path.abspath(temp_save_path)}", new=2)
                print(f"\n[Human Review] Please check iteration {iteration}  generated image.")
                print(f"AI score: {quality_score:.1f}/10")
                print("Please enter your score (0-10, press Enter to use AI score): ", end="")
                user_score_input = input().strip()
                if user_score_input:
                    try:
                        human_quality_score = float(user_score_input)
                        print(f"Using human score: {human_quality_score:.1f}/10")
                    except ValueError:
                        print("Invalid input, using AI score")
                        human_quality_score = None
                else:
                    print(f"Using AI score: {quality_score:.1f}/10")

                print("Please enter improvement suggestions for next iteration (press Enter to finish, leave empty to skip):")
                human_guidance_next = input().strip() or None
                if human_guidance_next:
                    print(f"Improvement suggestions recorded, will be used for next iteration")

                # Clean up temporary preview files
                if os.path.exists(temp_save_path):
                    os.remove(temp_save_path)
            except Exception as e:
                print(f"Unable to collect human feedback：{e}")

        # Determine effective score for this iteration
        if CONFIG.get('HUMAN_IN_LOOP', False):
            effective_score = human_quality_score if isinstance(human_quality_score, (int, float)) else quality_score
        else:
            effective_score = quality_score

        # ====== Save this iteration result ======
        improvement = effective_score - best_score
        saved_code_iter = save_iteration_results(
            iteration,
            improved_code,
            effective_score,
            output_dir,
            human_quality_score,
            human_guidance_next,
            evaluation_data=critique_result,
            output_format=output_format
        )

        if saved_code_iter:
            # Record to history
            iteration_history.append({
                'iteration': iteration,
                'quality_score': effective_score,
                'improvement': improvement,
                'critique': critique_result,
                'human_quality_score': human_quality_score,
                'human_guidance': human_guidance_next
            })

            # Update best result
            if effective_score > best_score:
                print(f"\nFound new best result! Quality improved from {best_score:.1f}  to  {effective_score:.1f}")
                best_code = saved_code_iter
                best_score = effective_score
                best_iteration_num = iteration
            else:
                print(f"This iteration score {effective_score:.1f} did not exceed best score {best_score:.1f}")

            # Update human guidance for next iteration
            human_guidance = human_guidance_next
        else:
            print(f"Iteration {iteration}  {format_name} invalid, cannot save. Keeping best result unchanged.")
            iteration_history.append({
                'iteration': iteration,
                'quality_score': None,
                'improvement': 0,
                'critique': critique_result
            })
        
        if best_score >= CONFIG['QUALITY_THRESHOLD']:
            print(f"Reached quality threshold of {CONFIG['QUALITY_THRESHOLD']}. Ending iterations early.")
            break
        
        if iteration > 1 and improvement < CONFIG['MIN_IMPROVEMENT'] and quality_score > best_score:
            print(f"Improvement margin ({improvement:.2f}) is smaller than the threshold {CONFIG['MIN_IMPROVEMENT']}. Convergence may be reached.")
    
    print("\nStep 5: Generating final results")

    final_code_content = best_code

    enable_user_selection = CONFIG.get('ENABLE_USER_SELECTION', False)
    selection_mode = CONFIG.get('SELECTION_MODE', 'auto')

    if enable_user_selection and selection_mode == 'user' and len(iteration_history) > 1:
        print(f"\nUser selection mode: Please select the most suitable {format_name} version")
        print("="*60)

        valid_iterations = []
        for i, hist in enumerate(iteration_history):
            if hist.get('quality_score') is not None:
                iteration_num = hist['iteration']
                score = hist['quality_score']
                png_path = os.path.join(output_dir, f'iteration_{iteration_num}.png')
                
                if os.path.exists(png_path):
                    valid_iterations.append({
                        'index': len(valid_iterations),
                        'iteration': iteration_num,
                        'score': score,
                        'png_path': png_path,
                        'code_path': os.path.join(output_dir, f'iteration_{iteration_num}{file_ext}')
                    })
                    
                    print(f"  [{len(valid_iterations)-1}] Iteration {iteration_num}:  score {score:.1f}/10")
                    
                    if CONFIG.get('AUTO_OPEN_IMAGES', False):
                        try:
                            os.startfile(png_path)  
                        except:
                            import webbrowser
                            webbrowser.open(f"file://{os.path.abspath(png_path)}")
        
        if valid_iterations:
            print(f"\nAI recommendation: Iteration {best_iteration_num} ( score: {best_score:.1f}/10)")
            print("Please enter version index (press Enter for AI recommendation):")
            
            try:
                user_choice = input("Select [0-{}]  or press Enter: ".format(len(valid_iterations)-1)).strip()
                
                if user_choice and user_choice.isdigit():
                    choice_idx = int(user_choice)
                    if 0 <= choice_idx < len(valid_iterations):
                        selected = valid_iterations[choice_idx]
                        print(f"User selected: Iteration {selected['iteration']} ( score: {selected['score']:.1f}/10)")

                        if os.path.exists(selected['code_path']):
                            with open(selected['code_path'], 'r', encoding='utf-8') as f:
                                final_code_content = f.read()
                            print(f"Loaded user selected {format_name}: Iteration {selected['iteration']}")
                        else:
                            print(f"Cannot find {format_name} file, using AI recommended version")
                    else:
                        print(f"Invalid selection, using AI recommended version")
                else:
                    print(f"Using AI recommendation: Iteration {best_iteration_num} ( score: {best_score:.1f}/10)")
            except KeyboardInterrupt:
                print(f"\nUser interrupted, using AI recommended version")
            except Exception as e:
                print(f"Selection process error, using AI recommended version: {e}")
        else:
            print("No valid iteration results to choose from, using best score version")
    else:
        print(f"Auto selection mode: Using highest scored{format_name} (Iteration {best_iteration_num},  score: {best_score:.1f}/10)")

    final_code_path = os.path.join(output_dir, f'figure_final{file_ext}')
    with open(final_code_path, 'w', encoding='utf-8') as f:
        f.write(final_code_content)

    final_png_path = os.path.join(output_dir, 'figure_final.png')
    success, _ = code_to_png(final_code_content, final_png_path, attempt_repair=False, output_format=output_format)
    if not success:
        print(f"The final {format_name} code has issues; could not generate the final PNG. Please check `figure_final{file_ext}`.")

    final_report = {
        'status': 'success' if success else 'finished_with_errors',
        'output_format': output_format,
        'final_quality_score': best_score,
        'total_iterations': len(iteration_history),
        'iteration_history': iteration_history,
        'output_files': {
            'final_code': final_code_path,
            'final_png': final_png_path if success else None,
            'output_directory': output_dir
        },
        'configuration': {k: v for k, v in CONFIG.items() if not k.endswith('_KEY')}  # Exclude API keys
    }

    report_path = os.path.join(output_dir, 'generation_report.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(final_report, f, indent=2, ensure_ascii=False)

    print("="*60)
    print(f"{format_name} scientific figure generation complete")
    print(f"Final Quality Score: {best_score:.1f}/10")
    print(f"Total Iterations: {len(iteration_history)}")
    print(f"Output Directory: {output_dir}")
    print(f"Final Code: {final_code_path}")
    print(f"Final Image: {final_png_path}")

    return final_report

if __name__ == "__main__":
    try:
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        references_dir = os.path.join(script_dir, 'references', 'paper')

        CONTENT_CONFIGS = {
            'paper': {
                'file': "paper.md",
                'description': "Research paper methodology",
                'references': [
                    os.path.join(references_dir, "exp_figure_5.png"),
                    os.path.join(references_dir, "exp_figure_6.png"),
                    os.path.join(references_dir, "exp_figure_7.png"),
                    os.path.join(references_dir, "exp_figure_10.png"),
                    os.path.join(references_dir, "exp_figure_ds.png"),
                ]
            },
            'survey': {
                'file': "survey.md",
                'description': "Literature survey overview",
                'references': []  # No survey references in opensource version
            },
            'blog': {
                'file': "blog.md",
                'description': "Blog post visualization",
                'references': []
            },
            'textbook': {
                'file': "textbook.md",
                'description': "Textbook content visualization",
                'references': []
            }
        }

        SELECTED_TOPIC = 'paper'

        print("LLM Provider: Bianxie (Only)")
        print(f"Bianxie Model: {CONFIG.get('BIANXIE_CHAT_MODEL', 'gemini-3.1-pro-preview')}")

        content_config = CONTENT_CONFIGS[SELECTED_TOPIC]
        content_file = content_config['file']
        reference_files = content_config['references']
        
        # Get output format from CONFIG
        output_format = CONFIG.get('OUTPUT_FORMAT', 'svg')
        format_name = 'mxGraph XML' if output_format == 'mxgraphxml' else 'SVG'
        file_ext = '.drawio' if output_format == 'mxgraphxml' else '.svg'

        preview_html_path = os.path.join(CONFIG['OUTPUT_DIR'], f'figure_final_preview_{SELECTED_TOPIC}.html')

        print(f"Selected content type: {SELECTED_TOPIC.upper()} ({content_config['description']})")
        print(f"Output format: {format_name}")
        print(f"Content file: {content_file}")
        print(f"Generating {SELECTED_TOPIC} layout...")

        if not os.path.exists(content_file):
            print(f"Content file not found: {content_file}")
        else:
            result = figure_generator_pipeline(
                paper_path=content_file,
                reference_figures=reference_files,
                topic=SELECTED_TOPIC,
                output_format=output_format
            )

            if result.get('status') == 'success':
                print("\nPipeline executed successfully!")
                final_code_path = result['output_files']['final_code']
                if final_code_path and os.path.exists(final_code_path):
                    try:
                        with open(final_code_path, 'r', encoding='utf-8') as f:
                            final_code_content = f.read()

                        # Generate HTML preview - different handling for SVG vs mxgraphxml
                        if output_format == 'svg':
                            # SVG can be embedded directly in HTML
                            embedded_content = final_code_content
                        else:
                            # mxgraphxml: show as code block with a note
                            embedded_content = f"""
  <div class="mxgraph-note">
    <p><strong>Note:</strong> mxGraph XML files can be opened in draw.io for editing.</p>
    <p>File: <code>{final_code_path}</code></p>
  </div>
  <pre class="code-preview"><code>{final_code_content[:5000]}{'...(truncated)' if len(final_code_content) > 5000 else ''}</code></pre>
"""

                        html_content = f"""
<!DOCTYPE html>
<html>
<head>
<title>{format_name} {SELECTED_TOPIC.title()} Layout Preview</title>
<style>
  body {{ font-family: sans-serif; }}
  .container {{ max-width: 1200px; margin: 20px auto; padding: 20px; border: 1px solid #ccc; box-shadow: 2px 2px 10px rgba(0,0,0,0.1); }}
  h1 {{ border-bottom: 2px solid #eee; padding-bottom: 10px; }}
  .info {{ background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
  .mxgraph-note {{ background: #e3f2fd; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #2196F3; }}
  .code-preview {{ background: #f5f5f5; padding: 15px; border-radius: 5px; overflow-x: auto; max-height: 500px; overflow-y: auto; }}
  code {{ font-family: 'Courier New', monospace; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <h1>{format_name} {SELECTED_TOPIC.title()} Layout Preview</h1>
  <div class="info">
    <strong>Content Type:</strong> {content_config['description']}<br>
    <strong>Output Format:</strong> {format_name}<br>
    <strong>Generation Date:</strong> {time.strftime('%Y-%m-%d %H:%M:%S')}<br>
    <strong>Final Quality Score:</strong> {result.get('final_quality_score', 'N/A')}/10<br>
    <strong>Total Iterations:</strong> {result.get('total_iterations', 'N/A')}
  </div>
  {embedded_content}
</div>
</body>
</html>
"""
                        with open(preview_html_path, 'w', encoding='utf-8') as f:
                            f.write(html_content)
                        print(f"View {format_name} result: {result['output_files']['final_code']}")
                        print(f"Browser preview: {preview_html_path}")

                    except Exception as e:
                        print(f"Failed to create HTML preview file: {e}")
                
            else:
                print(f"\nPipeline execution failed: {result.get('error', 'Unknown error')}")
                
    except Exception as e:
        print(f"An error occurred in the main process: {e}")
        import traceback
        traceback.print_exc() 
