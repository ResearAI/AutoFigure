"""
Image Enhancement Module for AutoFigure SDK.

Provides image enhancement/beautification capabilities using various
AI-powered services (BianXie, OpenRouter, Gemini).

This module mirrors the functionality in complete_pipeline_fixed.py.
"""

import os
import base64
import json
import time
import shutil
import re
from pathlib import Path
from typing import Optional, List, TYPE_CHECKING

import requests

from .utils.api_protocol import (
    GEMINI_NATIVE,
    chat_completions_url,
    default_base_url,
    normalize_gemini_base_url,
    normalize_protocol,
)
from .utils.llm_client import LLMClient

if TYPE_CHECKING:
    from .config import Config


def convert_code_to_text2image_prompt(
    source_code: str,
    art_style: str = "",
    content_type: str = "paper",
    code_format: str = "mxgraphxml",
    api_key: str = "",
    base_url: str = "",
    model: str = "",
    provider: str = "bianxie",
    protocol: Optional[str] = None,
) -> Optional[str]:
    """
    Convert code (mxgraphxml, HTML, etc.) to text2image prompt using LLM.

    This function uses an LLM to analyze the given code and generate a detailed
    prompt that can be used for image generation/enhancement.

    Args:
        source_code: The source code to convert
        art_style: Art style to apply in the generated prompt
        content_type: Type of content ('paper', 'survey', 'blog', 'textbook')
        code_format: Format of the code ('mxgraphxml', 'html', 'pptx')
        api_key: API key for the LLM provider
        base_url: Base URL for the API endpoint
        model: Model name to use
        provider: Provider name (bianxie, openrouter, gemini)

    Returns:
        Text2image prompt string, or None on failure
    """
    try:
        if not api_key:
            print("[Code2Prompt] ERROR: API key not provided!")
            return None

        print(f"[Code2Prompt] Converting {code_format.upper()} to image prompt...")
        print(f"[Code2Prompt] Art style: {art_style or '(default)'}")
        print(f"[Code2Prompt] Code length: {len(source_code)} chars")

        format_descriptions = {
            'pptx': 'Python-PPTX code that generates PowerPoint presentation slides',
            'html': 'HTML/CSS/JavaScript code that creates web-based visualizations',
            'mxgraphxml': 'mxGraph XML code (draw.io/diagrams.net format) that defines diagram layouts with shapes, connectors, and placeholder icons',
            'svg': 'SVG code that defines vector graphics'
        }

        format_specific_instructions = {
            'pptx': """
**PPTX CODE ANALYSIS FOCUS:**
- Analyze the PowerPoint slide structure and layout
- Identify text boxes, shapes, and visual elements
- Extract positioning information (coordinates, dimensions)
- Understand the presentation flow and hierarchy
- Convert programmatic slide creation into visual descriptions
""",
            'html': """
**HTML CODE ANALYSIS FOCUS:**
- Parse the HTML DOM structure and CSS styling
- Identify visual elements: divs, spans, SVG elements, canvas
- Extract layout information: flexbox, grid, positioning
- Analyze CSS colors, fonts, and visual effects
- Convert web layout markup into visual descriptions
""",
            'mxgraphxml': """
**MXGRAPH XML CODE ANALYSIS FOCUS:**
- Parse the mxGraph XML structure: mxfile > diagram > mxGraphModel > root > mxCell elements
- Identify gray placeholder rectangles by their style attributes containing `fillColor=#808080` or `fillColor=gray` or similar gray colors
- **CRITICAL**: Extract the `value` attribute of each gray placeholder mxCell - this contains the icon description in format `[icon]: <detailed description>`
- Parse geometry information (x, y, width, height) from mxGeometry elements
- Identify connector arrows (mxCell elements with `source` and `target` attributes)
- Identify text labels (mxCell elements with `value` attribute containing non-icon text)
- Understand the flow direction from arrow connections
- Note: Placeholders are mxCell elements with gray fillColor and contain `[icon]:` prefix in their value attribute
""",
            'svg': """
**SVG CODE ANALYSIS FOCUS:**
- Parse the SVG structure including groups, paths, and shapes
- Identify all visual elements and their attributes
- Extract positioning, sizing, and styling information
- Understand the visual hierarchy and connections
- Convert vector graphics into visual descriptions
"""
        }

        conversion_prompt = f"""You are an expert visual design analyst specializing in converting technical code into detailed text-to-image prompts. Your task is to analyze the provided {format_descriptions.get(code_format, 'code')} and create a comprehensive prompt that will guide AI image generation to produce a professional, visually stunning scientific illustration.

**PRIMARY OBJECTIVE:**
Create a text-to-image prompt that will transform the programmatic layout defined in the {code_format.upper()} code into a beautiful visual illustration while maintaining perfect layout structure and applying the specified artistic style: "{art_style}".

**ARTISTIC STYLE INTEGRATION:**
The final illustration MUST strictly follow this artistic style: "{art_style}"
- All visual elements, colors, effects, and overall aesthetic must align with this style
- Icons and visual components should be designed to match this artistic direction
- Color palette, typography, and visual effects should complement this style
- The overall composition should embody the essence of "{art_style}"

{format_specific_instructions.get(code_format, '')}

**CRITICAL ANALYSIS STEPS:**

1. **Code Structure Analysis:**
   - Parse the {code_format.upper()} code to understand the intended visual layout
   - Identify all visual elements defined in the code
   - Extract positioning, sizing, and styling information
   - Understand the overall composition and flow

2. **Visual Element Identification:**
   - Locate all shapes, text elements, and containers
   - Identify placeholder areas that need icon conversion
   - Document spatial relationships between elements
   - Note any special styling or effects

3. **Style-Specific Visual Enhancement Requirements:**
   - Apply "{art_style}" consistently throughout the design
   - Define color schemes that match the specified artistic style
   - Specify visual hierarchy and emphasis appropriate for the style
   - Describe background treatment that complements the artistic direction

**OUTPUT FORMAT REQUIREMENTS:**

Your response must include these EXACT sections:

**SECTION 1: OVERALL SCENE DESCRIPTION**
"A professional {content_type} methodology diagram based on {code_format.upper()} code structure. The illustration should be rendered in the '{art_style}' style with [style-appropriate color palette and visual characteristics]. The layout follows [describe flow pattern from code analysis]. The overall aesthetic perfectly embodies the '{art_style}' artistic direction."

**SECTION 2: VISUAL ELEMENTS FROM CODE**
For each visual element found in the code, provide:
"Element [description from code]: Render as [VERY SPECIFIC visual description that incorporates '{art_style}' style elements]. The element should be [size and position from code], styled in '{art_style}' with [specific style characteristics: colors, effects, textures, etc.]. It represents [concept] and should visually communicate [specific meaning] while perfectly matching the '{art_style}' aesthetic."

**SECTION 3: TEXT ELEMENTS TO PRESERVE**
"The following text must appear exactly as specified in the code, styled to match '{art_style}': [list all text content with position descriptions and style-appropriate typography specifications]"

**SECTION 4: ARTISTIC STYLE IMPLEMENTATION**
"The entire illustration must be rendered in the '{art_style}' style. Specific implementation requirements:
- Color Palette: [define colors that match the artistic style]
- Visual Effects: [specify effects appropriate for the style: shadows, gradients, textures, etc.]
- Typography: [describe text styling that complements the artistic direction]
- Overall Aesthetic: [detailed description of how the '{art_style}' should be applied]
- Visual Characteristics: [specific visual elements that define this artistic style]"

**SECTION 5: LAYOUT AND CONNECTIONS**
"Maintain these exact spatial relationships from the {code_format.upper()} code: [describe arrangement]. Connect elements with [connection specifications styled to match '{art_style}']. Ensure [spacing and alignment from code]. All elements should be rendered in '{art_style}' style."

**CRITICAL SUCCESS FACTORS:**
- Every programmatic element MUST be converted to a specific, implementable visual description that matches '{art_style}'
- All text content defined in the code MUST be preserved with style-appropriate formatting
- Layout structure from the {code_format.upper()} code MUST be maintained exactly
- The '{art_style}' style MUST be consistently applied throughout all visual elements
- Style specifications MUST be detailed enough for consistent application
- The prompt MUST be actionable for AI image generation in the specified artistic style

**INPUT {code_format.upper()} CODE:**
```{code_format}
{source_code}
```

**ARTISTIC STYLE TO APPLY:** "{art_style}"

Now analyze this {code_format.upper()} code and create the comprehensive text-to-image prompt following the exact format above. Focus especially on converting every programmatic element into a specific, detailed visual description that perfectly matches the "{art_style}" artistic style while maintaining visual clarity and professional quality."""

        effective_protocol = normalize_protocol(provider, protocol)
        actual_base_url = base_url or default_base_url(provider, effective_protocol)

        print(f"[Code2Prompt] Using provider: {provider}, protocol: {effective_protocol}, model: {model}")

        client = LLMClient(
            api_key=api_key,
            base_url=actual_base_url,
            model=model,
            provider=provider,
            protocol=effective_protocol,
        )
        response = client.call([conversion_prompt], temperature=0.7)
        if response and len(response.strip()) > 0:
            print(f"[Code2Prompt] Generated prompt length: {len(response)} chars")
            return response.strip()

        print("[Code2Prompt] LLM returned empty response")
        return None

    except Exception as e:
        print(f"[Code2Prompt] Conversion failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def _save_base64_image_from_markdown(markdown_content: str, output_path: str) -> bool:
    """
    Extract and save base64 image from markdown format.
    Format: ![image](data:image/png;base64,<data>)
    """
    try:
        pattern = r'data:image/(png|jpeg|jpg|webp);base64,([A-Za-z0-9+/=]+)'
        match = re.search(pattern, markdown_content)
        if match:
            image_data = match.group(2)
            image_bytes = base64.b64decode(image_data)
            with open(output_path, 'wb') as f:
                f.write(image_bytes)
            return True
        return False
    except Exception as e:
        print(f"[SaveImage] Failed to extract image: {e}")
        return False


class ImageEnhancer:
    """
    Enhances generated figures using AI image enhancement services.

    Supports providers:
    - bianxie: Uses BianXie AI API (OpenAI-compatible)
    - openrouter: Uses OpenRouter API (requires modalities parameter)
    - gemini: Uses Google Gemini native API
    """

    def __init__(self, config: "Config"):
        """
        Initialize the image enhancer.

        Args:
            config: AutoFigure SDK configuration
        """
        self.config = config

    def enhance(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        enhancement_input: str = "",
        style: Optional[str] = None,
        input_type: str = "code2prompt",
    ) -> Optional[str]:
        """
        Enhance an image file using the configured provider.

        Args:
            input_path: Path to the input image (PNG)
            output_path: Path for the enhanced output (optional)
            enhancement_input: Enhancement prompt or code
            style: Art style for enhancement
            input_type: 'none' | 'code' | 'code2prompt'
                - 'none': Direct visual enhancement without code reference
                - 'code': Use code as reference (svg_code mode)
                - 'code2prompt': Use LLM-generated detailed prompt

        Returns:
            Path to the enhanced image, or None on failure
        """
        api_key = self.config.enhancement_api_key
        if not api_key:
            print("[ImageEnhancer] No enhancement API key configured, skipping enhancement")
            return None

        input_path = Path(input_path)
        if not input_path.exists():
            print(f"[ImageEnhancer] Input file not found: {input_path}")
            return None

        # Default output path
        if output_path is None:
            output_path = str(input_path.parent / f"{input_path.stem}_enhanced.png")

        provider = self.config.enhancement_provider
        protocol = normalize_protocol(provider, getattr(self.config, "enhancement_protocol", None))
        model = self.config.enhancement_model
        base_url = self.config.enhancement_base_url
        art_style = style or self.config.art_style or ""

        print(f"[ImageEnhancer] Provider: {provider}")
        print(f"[ImageEnhancer] Protocol: {protocol}")
        print(f"[ImageEnhancer] Model: {model}")
        print(f"[ImageEnhancer] Style: {art_style or '(default)'}")
        print(f"[ImageEnhancer] Input type: {input_type}")

        # Route to provider-specific function
        if protocol == GEMINI_NATIVE:
            return self._enhance_with_gemini(
                str(input_path), enhancement_input, output_path,
                style=art_style, input_type=input_type,
                api_key=api_key, base_url=base_url, model=model
            )
        elif provider == "openrouter":
            return self._enhance_with_openrouter(
                str(input_path), enhancement_input, output_path,
                style=art_style, input_type=input_type,
                api_key=api_key, base_url=base_url, model=model
            )
        else:  # OpenAI-compatible (BianXie/custom/default)
            return self._enhance_with_bianxie(
                str(input_path), enhancement_input, output_path,
                style=art_style, input_type=input_type,
                api_key=api_key, base_url=base_url, model=model
            )

    def _build_enhancement_prompt(
        self,
        style: str,
        enhancement_input: str,
        input_type: str,
    ) -> str:
        """Build the enhancement prompt based on input type."""
        selected_style = style if style else "Modern scientific illustration"

        if input_type == "none":
            # Direct visual enhancement - no code reference
            return f"""**BACKGROUND & PURPOSE:**
You are a world-class scientific illustrator specializing in academic research visualizations. Your task is to transform a black-and-white layout diagram into a professional, publication-ready scientific illustration for academic journals and educational materials.

**ARTISTIC STYLE APPLICATION:**
The entire illustration MUST be rendered in the following artistic style: "{selected_style}"
- Apply this style consistently across all visual elements
- Use colors, textures, and effects that align with "{selected_style}"
- Maintain visual coherence throughout the composition
- Ensure the style enhances readability and professional appearance

**STEP-BY-STEP TRANSFORMATION PROCESS:**

**Step 1: Layout Structure Analysis**
Carefully examine the provided layout diagram (originally generated from mxGraph XML / draw.io format) and identify:
- Rectangular boxes and containers (preserve exact positions and proportions)
- Connecting arrows and flow lines (maintain direction and visual hierarchy)
- Text labels positioned outside placeholder areas
- Gray placeholder rectangles - these are icon placeholders that contain descriptive text starting with "[icon]:" prefix

**Step 2: Understanding Placeholder Structure**
This diagram was generated from mxGraph XML (draw.io format). Gray rectangles are icon placeholders:
- **Identification**: Gray-colored rectangular areas containing text that describes what icon should replace them
- **Format**: The placeholder text follows the format "[icon]: <description>" where <description> explains what icon to create
- **Purpose**: These placeholders reserve space and provide instructions - they must be replaced with actual icons

**Step 3: Text Element Processing**
- **External Text (PRESERVE EXACTLY)**: All black text positioned outside gray placeholders represents final labels, titles, and annotations. These MUST appear in the finished illustration with PERFECT accuracy - do not modify, rephrase, or omit any external text
- **Internal Placeholder Text (CONVERT TO ICONS)**: Text inside gray rectangles serves as icon creation instructions. The text after "[icon]:" describes what visual icon should replace the gray box. Transform these descriptions into appropriate visual icons, completely removing the instructional text

**Step 4: Visual Element Enhancement**
Transform layout elements following "{selected_style}" specifications:
- **Boxes**: Convert plain rectangles into styled containers with appropriate colors, borders, and visual effects matching "{selected_style}"
- **Arrows**: Create elegant directional indicators with consistent styling, appropriate thickness, and visual appeal
- **Connections**: Maintain all spatial relationships while enhancing visual flow

**Step 5: Icon Creation Process**
For each gray placeholder area containing "[icon]: <description>":
- Read the description text after "[icon]:" carefully - this tells you what icon to create
- Design a clear, professional icon that visually represents the described concept
- Apply "{selected_style}" aesthetic to the icon design
- Ensure icons are appropriately sized and positioned within their designated placeholder areas
- Use colors and design elements consistent with the overall style
- The icon should be self-explanatory and convey the concept without needing text

**Step 6: Typography and Text Rendering**
- Render all external text labels with crystal-clear readability
- Use typography that complements "{selected_style}"
- Maintain original text positioning and hierarchy
- Apply consistent font weights and sizes appropriate for the artistic style

**CRITICAL QUALITY REQUIREMENTS:**
- High-resolution output suitable for academic publication (minimum 1200x800 pixels)
- Professional color harmony matching "{selected_style}"
- Perfect structural fidelity to the original layout
- Every gray placeholder MUST be replaced with an appropriate icon based on its "[icon]:" description
- All icons must be contextually appropriate and visually clear
- Zero placeholder instruction text (no "[icon]:" text) in the final output
- All external labels must be preserved with perfect accuracy
- Consistent visual style across all elements

**OUTPUT SPECIFICATIONS:**
Create a stunning scientific illustration that perfectly balances the "{selected_style}" aesthetic with academic professionalism, ensuring every visual element serves both artistic and informational purposes.

Transform the provided layout into this enhanced visualization now."""

        elif input_type == "code":
            # Use code as reference (svg_code mode)
            return f"""**BACKGROUND & PURPOSE:**
You are a world-class scientific illustrator specializing in academic research visualizations. Your task is to transform a black-and-white layout diagram into a professional, publication-ready scientific illustration for academic journals and educational materials.

**ARTISTIC STYLE APPLICATION:**
The entire illustration MUST be rendered in the following artistic style: "{selected_style}"
- Apply this style consistently across all visual elements
- Use colors, textures, and effects that align with "{selected_style}"
- Maintain visual coherence throughout the composition
- Ensure the style enhances readability and professional appearance

**TECHNICAL REFERENCE (Code Structure):**
Use this code to understand the precise layout structure, element relationships, and spatial positioning:
```
{enhancement_input[:5000] if enhancement_input else '(no code provided)'}
```

**STEP-BY-STEP TRANSFORMATION PROCESS:**

**Step 1: Code Structure Analysis**
Parse the provided code to identify:
- Exact coordinates and dimensions of all elements
- Text positioning and content hierarchy
- Shape relationships and visual flow patterns
- Color specifications and styling attributes

**Step 2: Layout Preservation**
Maintain absolute fidelity to:
- Element positions and proportions from code coordinates
- Text placement and alignment specifications
- Arrow paths and connection points
- Overall composition balance and spacing

**Step 3: Text Element Processing**
- **External Text (PRESERVE)**: All text positioned outside gray placeholder areas represents final labels that must appear with perfect accuracy
- **Internal Placeholder Text (CONVERT)**: Text inside gray rectangles serves as icon creation instructions - transform these descriptions into appropriate visual icons

**Step 4: Style-Conscious Enhancement**
Apply "{selected_style}" while preserving code structural integrity:
- **Color Palette**: Select colors that embody "{selected_style}" aesthetic
- **Visual Effects**: Add appropriate shadows, gradients, or textures consistent with the style
- **Typography**: Choose fonts and text styling that complement "{selected_style}"
- **Icon Design**: Create icons that match both the functional requirements and artistic direction

**Step 5: Professional Icon Creation**
For each placeholder identified in the code:
- Extract the descriptive instruction text
- Design contextually appropriate icons in "{selected_style}"
- Ensure icons integrate seamlessly with the overall composition
- Maintain clear visual communication of each concept

**CRITICAL QUALITY REQUIREMENTS:**
- High-resolution output suitable for academic publication
- Perfect adherence to code layout specifications
- Professional color harmony matching "{selected_style}"
- All icons contextually appropriate and visually clear
- Zero placeholder instruction text in final output
- Consistent "{selected_style}" aesthetic throughout

**OUTPUT SPECIFICATIONS:**
Create a stunning scientific illustration that perfectly balances the "{selected_style}" aesthetic with the precise structure defined in the code, ensuring every visual element serves both artistic and informational purposes.

Transform the provided layout into this enhanced visualization now."""

        else:  # code2prompt (text2image_prompt)
            # Use LLM-generated detailed prompt
            return f"""**BACKGROUND & PURPOSE:**
You are a world-class scientific illustrator specializing in academic research visualizations. Your task is to transform a black-and-white layout diagram into a professional, publication-ready scientific illustration for academic journals and educational materials.

**ARTISTIC STYLE APPLICATION:**
The entire illustration MUST be rendered in the following artistic style: "{selected_style}"
- Apply this style consistently across all visual elements
- Use colors, textures, and effects that align with "{selected_style}"
- Maintain visual coherence throughout the composition
- Ensure the style enhances readability and professional appearance

**COMPREHENSIVE VISUAL SPECIFICATIONS:**
Follow these detailed requirements for creating the enhanced illustration:

```
{enhancement_input if enhancement_input else '(no specifications provided)'}
```

**STEP-BY-STEP EXECUTION PROCESS:**

**Step 1: Specification Analysis**
Carefully review the detailed visual specifications above to understand:
- Overall scene composition and flow patterns
- Specific placeholder-to-icon conversion requirements
- Text elements that must be preserved exactly
- Style-specific implementation guidelines

**Step 2: Layout Structure Implementation**
Based on the specifications:
- Maintain exact spatial relationships as described
- Preserve all text positioning and hierarchy requirements
- Follow the specified color palette and visual characteristics
- Implement the described connection patterns and flow directions

**Step 3: Style-Conscious Icon Development**
For each icon conversion specified:
- Create detailed icons that match both the functional description and "{selected_style}"
- Ensure visual consistency across all icon elements
- Apply appropriate sizing and positioning as specified
- Use colors and effects that harmonize with the overall artistic direction

**Step 4: Typography and Text Rendering**
- Render preserved text elements with crystal-clear readability
- Apply typography styling that complements "{selected_style}"
- Maintain specified text positioning and visual hierarchy
- Ensure perfect accuracy of all preserved text content

**Step 5: Final Style Integration**
Unify all elements under the "{selected_style}" aesthetic:
- Apply consistent visual effects (shadows, gradients, textures)
- Ensure harmonious color relationships throughout
- Balance artistic appeal with professional functionality
- Optimize for academic publication standards

**CRITICAL QUALITY REQUIREMENTS:**
- High-resolution output suitable for academic publication
- Perfect adherence to detailed visual specifications
- Professional implementation of "{selected_style}"
- All icons contextually appropriate and visually stunning
- Zero placeholder instruction text in final output
- Seamless integration of all visual elements

**OUTPUT SPECIFICATIONS:**
Create a masterful scientific illustration that flawlessly implements both the detailed visual specifications and the "{selected_style}" artistic direction, resulting in a publication-ready visualization that exceeds professional standards.

Transform the provided layout into this enhanced visualization now."""

    def _enhance_with_bianxie(
        self,
        input_path: str,
        enhancement_input: str,
        output_path: str,
        style: str = "",
        input_type: str = "code2prompt",
        api_key: str = None,
        base_url: str = None,
        model: str = None,
    ) -> Optional[str]:
        """
        Enhance image using BianXie API.

        BianXie API format (OpenAI-compatible chat completions):
        - Endpoint: https://api.bianxie.ai/v1/chat/completions
        - Image uploaded via base64 in image_url content type
        - Response: Image returned as base64 in markdown format within content
        """
        try:
            if not api_key:
                print("[BianXie] ERROR: API key not provided!")
                return None

            if not model:
                model = "gemini-3.1-flash-image-preview"

            actual_base_url = chat_completions_url(base_url or "https://api.bianxie.ai/v1")

            print(f"[BianXie] API: {actual_base_url}")
            print(f"[BianXie] Model: {model}")

            # Read and encode the input image
            with open(input_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")

            # Build enhancement prompt
            prompt = self._build_enhancement_prompt(style, enhancement_input, input_type)

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

            data = {
                "model": model,
                "stream": False,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                            },
                        ],
                    }
                ],
            }

            print("[BianXie] Calling image enhancement API...")
            response = requests.post(actual_base_url, headers=headers, json=data, timeout=300)

            if response.status_code != 200:
                print(f"[BianXie] API error: {response.status_code} - {response.text[:500]}")
                return None

            result = response.json()
            return self._extract_image_from_openai_response(result, output_path, input_path, "BianXie")

        except Exception as e:
            print(f"[BianXie] Enhancement failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _enhance_with_openrouter(
        self,
        input_path: str,
        enhancement_input: str,
        output_path: str,
        style: str = "",
        input_type: str = "code2prompt",
        api_key: str = None,
        base_url: str = None,
        model: str = None,
    ) -> Optional[str]:
        """
        Enhance image using OpenRouter API.

        OpenRouter API format:
        - Endpoint: https://openrouter.ai/api/v1/chat/completions
        - MUST include modalities: ["image", "text"] to enable image generation
        - Image uploaded via base64 in image_url content type
        - Response: Images returned in message["images"] array as base64 data URLs
        """
        try:
            if not api_key:
                print("[OpenRouter] ERROR: API key not provided!")
                return None

            if not model:
                model = "google/gemini-3.1-flash-image-preview"

            actual_base_url = chat_completions_url(base_url or "https://openrouter.ai/api/v1")

            print(f"[OpenRouter] API: {actual_base_url}")
            print(f"[OpenRouter] Model: {model}")

            # Read and encode the input image
            with open(input_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")

            # Build enhancement prompt
            prompt = self._build_enhancement_prompt(style, enhancement_input, input_type)

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

            # OpenRouter requires modalities parameter for image generation
            data = {
                "model": model,
                "modalities": ["image", "text"],
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                            },
                        ],
                    }
                ],
            }

            print("[OpenRouter] Calling image enhancement API...")
            response = requests.post(actual_base_url, headers=headers, json=data, timeout=300)

            if response.status_code != 200:
                print(f"[OpenRouter] API error: {response.status_code} - {response.text[:500]}")
                return None

            result = response.json()
            return self._extract_image_from_openai_response(result, output_path, input_path, "OpenRouter")

        except Exception as e:
            print(f"[OpenRouter] Enhancement failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _enhance_with_gemini(
        self,
        input_path: str,
        enhancement_input: str,
        output_path: str,
        style: str = "",
        input_type: str = "code2prompt",
        api_key: str = None,
        base_url: str = None,
        model: str = None,
    ) -> Optional[str]:
        """
        Enhance image using Google Gemini native API.

        Gemini API uses a different format than OpenAI-compatible APIs:
        - URL: {base_url}/models/{model}:generateContent?key={api_key}
        - Request uses 'contents' with 'parts' instead of 'messages'
        - Response contains 'candidates' with 'content.parts' containing 'inlineData'
        """
        try:
            if not api_key:
                print("[Gemini] ERROR: API key not provided!")
                return None

            if not model:
                model = "gemini-3.1-flash-image-preview"

            # Construct Gemini API URL
            if not base_url:
                base_url = "https://generativelanguage.googleapis.com/v1beta"

            api_url = f"{normalize_gemini_base_url(base_url)}/models/{model}:generateContent?key={api_key}"

            print(f"[Gemini] Model: {model}")
            print(f"[Gemini] Input type: {input_type}")

            # Read and encode the input image
            with open(input_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")

            # Build enhancement prompt
            prompt = self._build_enhancement_prompt(style, enhancement_input, input_type)

            headers = {
                "Content-Type": "application/json"
            }

            # Gemini API request format with image input
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": prompt},
                            {
                                "inlineData": {
                                    "mimeType": "image/png",
                                    "data": image_base64
                                }
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "responseModalities": ["image", "text"]
                }
            }

            print("[Gemini] Calling image enhancement API...")
            response = requests.post(api_url, headers=headers, json=payload, timeout=300)

            if response.status_code != 200:
                print(f"[Gemini] API error: {response.status_code} - {response.text[:500]}")
                return None

            result = response.json()

            # Check for API errors
            if "error" in result:
                error_msg = result.get("error", {})
                if isinstance(error_msg, dict):
                    error_msg = error_msg.get("message", str(error_msg))
                print(f"[Gemini] API error: {error_msg}")
                return None

            # Extract from candidates
            candidates = result.get("candidates", [])
            if not candidates:
                print("[Gemini] No candidates in response")
                return None

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])

            print(f"[Gemini] Found {len(parts)} parts in response")

            # Look for inlineData (image) in parts
            for part in parts:
                if "inlineData" in part:
                    inline_data = part["inlineData"]
                    image_data_b64 = inline_data.get("data", "")

                    if image_data_b64:
                        # Decode and save the image
                        image_bytes = base64.b64decode(image_data_b64)

                        from PIL import Image
                        import io

                        img = Image.open(io.BytesIO(image_bytes))
                        img.save(output_path, "PNG")

                        print(f"[Gemini] Image saved to: {output_path}")
                        return output_path

            # Fallback: check for data URL in text parts
            for part in parts:
                if "text" in part:
                    text = part["text"]
                    if _save_base64_image_from_markdown(text, output_path):
                        print(f"[Gemini] Image extracted from text and saved to: {output_path}")
                        return output_path

            print("[Gemini] No image found in response")
            return None

        except Exception as e:
            print(f"[Gemini] Enhancement failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _extract_image_from_openai_response(
        self,
        result: dict,
        output_path: str,
        input_path: str,
        provider_name: str,
    ) -> Optional[str]:
        """
        Extract image from OpenAI-compatible API response (BianXie/OpenRouter format).
        """
        image_saved = False

        if "choices" in result and len(result["choices"]) > 0:
            message = result["choices"][0].get("message", {})

            # Check for images array (OpenRouter format)
            if "images" in message and isinstance(message["images"], list):
                for img in message["images"]:
                    if isinstance(img, dict) and "image_url" in img:
                        image_url = img["image_url"].get("url", "")
                        if image_url.startswith("data:image/"):
                            try:
                                base64_data = image_url.split(",", 1)[1]
                                image_bytes = base64.b64decode(base64_data)
                                with open(output_path, "wb") as f:
                                    f.write(image_bytes)
                                image_saved = True
                                print(f"[{provider_name}] Extracted image from message.images")
                                break
                            except Exception as e:
                                print(f"[{provider_name}] Failed to decode image: {e}")

            # Fallback: Check content for embedded images
            if not image_saved:
                content = message.get("content", "")
                if isinstance(content, str) and "data:image/" in content:
                    if _save_base64_image_from_markdown(content, output_path):
                        image_saved = True
                        print(f"[{provider_name}] Extracted image from markdown content")

                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            if part.get("type") == "image_url":
                                url = part.get("image_url", {}).get("url", "")
                                if url.startswith("data:image/"):
                                    try:
                                        base64_data = url.split(",", 1)[1]
                                        image_bytes = base64.b64decode(base64_data)
                                        with open(output_path, "wb") as f:
                                            f.write(image_bytes)
                                        image_saved = True
                                        print(f"[{provider_name}] Extracted image from content list")
                                        break
                                    except Exception:
                                        pass
                            elif "data" in part:
                                # Direct base64 data
                                try:
                                    image_bytes = base64.b64decode(part["data"])
                                    with open(output_path, "wb") as f:
                                        f.write(image_bytes)
                                    image_saved = True
                                    print(f"[{provider_name}] Extracted image from data field")
                                    break
                                except Exception:
                                    pass

        # Check for DALL-E style response
        if not image_saved and "data" in result and isinstance(result["data"], list):
            for item in result["data"]:
                if "b64_json" in item:
                    try:
                        image_bytes = base64.b64decode(item["b64_json"])
                        with open(output_path, "wb") as f:
                            f.write(image_bytes)
                        image_saved = True
                        print(f"[{provider_name}] Extracted image from data.b64_json")
                        break
                    except Exception:
                        pass

        if image_saved:
            print(f"[{provider_name}] Image enhancement successful: {output_path}")
            return output_path
        else:
            # Save response for debugging
            debug_path = output_path.replace(".png", f"_{provider_name.lower()}_response.json")
            with open(debug_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"[{provider_name}] No image in response, debug saved: {debug_path}")

            # Copy original as fallback
            shutil.copy2(input_path, output_path)
            print(f"[{provider_name}] Copied original as fallback: {output_path}")
            return None

    def is_available(self) -> bool:
        """Check if enhancement is available (API key configured)."""
        return bool(self.config.enhancement_api_key)
