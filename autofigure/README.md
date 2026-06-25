# AutoFigure

AI-powered Scientific Figure Generation - Generate professional scientific figures with just a few lines of code.

## Features

- **Simple API**: Generate figures from text descriptions or papers
- **Multiple Formats**: Output SVG and mxGraph XML (draw.io compatible)
- **Image Enhancement**: Optional AI-powered image beautification with multiple variants
- **Multiple Providers**: Support for OpenRouter, Requesty, Bianxie, Gemini
- **Content Types**: Optimized for papers, surveys, blogs, and textbooks

## Installation

```bash
# Basic installation
pip install autofigure

# With PDF support
pip install autofigure[pdf]

# With image enhancement
pip install autofigure[enhancement]

# Full installation
pip install autofigure[full]
```

Or install from source:

```bash
git clone https://github.com/ResearAI/AutoFigure
cd autofigure
pip install -e .
```

## Quick Start

### Basic Usage

```python
from autofigure import AutoFigureAgent, Config

# Create configuration with your API key
config = Config(
    generation_api_key="your-openrouter-api-key",
    generation_provider="openrouter",  # or 'bianxie', 'gemini'
    generation_model="google/gemini-3.1-pro-preview",
)

# Create agent
agent = AutoFigureAgent(config)

# Generate figure from description
result = agent.generate(
    description="A flowchart showing the training pipeline of a transformer model",
    max_iterations=5,
    output_format="svg",  # 'svg' or 'mxgraphxml'
    topic="paper",  # 'paper', 'survey', 'blog', 'textbook'
)

if result.success:
    print(f"SVG: {result.svg_path}")
    print(f"Preview: {result.preview_path}")
    print(f"Score: {result.final_score}/10")
else:
    print(f"Error: {result.error}")
```

### Generate from Paper

Extract methodology from a paper (PDF or Markdown) and generate a figure:

```python
from autofigure import AutoFigureAgent, Config

config = Config(
    generation_api_key="your-api-key",
    generation_model="google/gemini-3.1-pro-preview",

    # Methodology extraction settings (optional, defaults to generation settings)
    methodology_api_key="your-methodology-api-key",
    methodology_provider="openrouter",
    methodology_model="google/gemini-3.1-pro-preview",
)

agent = AutoFigureAgent(config)

# Generate figure from paper (PDF or Markdown)
result = agent.generate_from_paper(
    paper_path="./paper.pdf",
    max_iterations=5,
    output_format="svg",
    enable_enhancement=True,
)

if result.success:
    print(f"Extracted methodology: {result.methodology_text[:200]}...")
    print(f"Generated figure: {result.svg_path}")
```

You can also override methodology settings at call time:

```python
result = agent.generate_from_paper(
    paper_path="./paper.pdf",
    methodology_api_key="different-api-key",  # Override config
    methodology_model="google/gemini-3.1-pro-preview",
)
```

### With Image Enhancement

Generate multiple enhanced image variants:

```python
from autofigure import AutoFigureAgent, Config

config = Config(
    generation_api_key="your-api-key",
    generation_model="google/gemini-3.1-pro-preview",

    # Enhancement settings
    enhancement_api_key="your-enhancement-api-key",
    enhancement_provider="openrouter",
    enhancement_model="google/gemini-3.1-flash-image-preview",
    enhancement_input_type="code2prompt",  # 'none', 'code', 'code2prompt'
    enhancement_count=3,  # Generate 3 enhanced variants
    art_style="Modern scientific illustration with clean lines and professional colors",
)

agent = AutoFigureAgent(config)

result = agent.generate(
    description="Neural network architecture diagram",
    enable_enhancement=True,
    enhancement_count=3,  # Can override config at call time
)

if result.success:
    print(f"Preview: {result.preview_path}")
    print(f"First enhanced: {result.enhanced_path}")
    print(f"All enhanced images ({len(result.enhanced_paths)}):")
    for path in result.enhanced_paths:
        print(f"  - {path}")
```

### Generate from Content File

```python
from autofigure import AutoFigureAgent, Config

config = Config(generation_api_key="your-api-key")
agent = AutoFigureAgent(config)

# Generate from markdown/text file
result = agent.generate_from_file(
    content_path="./methodology.md",
    topic="paper",  # 'paper', 'survey', 'blog', 'textbook'
    enable_enhancement=True,
    enhancement_count=3,
)
```

## Configuration Options

### Generation Settings

| Option | Description | Default |
|--------|-------------|---------|
| `generation_api_key` | API key for figure generation | Required |
| `generation_base_url` | Base URL for API | Provider default |
| `generation_model` | Model name | Provider default |
| `generation_provider` | Provider: 'openrouter', 'requesty', 'bianxie', 'gemini' | 'openrouter' |

Bianxie users can register at [bianxieai](https://bianxieai.com/autofigure). The Bianxie API uses the default base URL `https://api.bianxie.ai/v1`.

Requesty is an OpenAI-compatible LLM gateway; with `generation_provider="requesty"` the default base URL is `https://router.requesty.ai/v1`.

### Methodology Extraction Settings

| Option | Description | Default |
|--------|-------------|---------|
| `methodology_api_key` | API key for methodology extraction | Same as generation |
| `methodology_base_url` | Base URL for methodology API | Same as generation |
| `methodology_model` | Model for methodology extraction | Same as generation |
| `methodology_provider` | Provider for methodology extraction | Same as generation |

### Enhancement Settings

| Option | Description | Default |
|--------|-------------|---------|
| `enhancement_api_key` | API key for image enhancement | None |
| `enhancement_provider` | Enhancement provider | 'openrouter' |
| `enhancement_model` | Model for image enhancement | Provider default |
| `enhancement_base_url` | Base URL for enhancement API | Provider default |
| `enhancement_input_type` | Input type: 'none', 'code', 'code2prompt' | 'code2prompt' |
| `enhancement_count` | Number of enhanced variants to generate | 1 |
| `art_style` | Art style description for enhancement | '' |

### Pipeline Settings

| Option | Description | Default |
|--------|-------------|---------|
| `max_iterations` | Maximum refinement iterations | 5 |
| `quality_threshold` | Quality threshold (0-10) | 9.0 |
| `output_dir` | Output directory | './autofigure_output' |
| `custom_references` | Custom reference figure paths | None (uses built-in) |

## Method Parameters

### `generate()` Parameters

| Parameter | Description |
|-----------|-------------|
| `description` | Text description of the figure to generate |
| `max_iterations` | Maximum iterations (overrides config) |
| `output_format` | 'svg' or 'mxgraphxml' |
| `quality_threshold` | Quality threshold (overrides config) |
| `enable_enhancement` | Whether to enhance the final image |
| `art_style` | Art style for enhancement (overrides config) |
| `enhancement_input_type` | 'none', 'code', or 'code2prompt' (overrides config) |
| `enhancement_count` | Number of enhanced variants (overrides config) |
| `topic` | Content type: 'paper', 'survey', 'blog', 'textbook' |
| `custom_references` | Custom reference figure paths |
| `output_dir` | Output directory (overrides config) |

### `generate_from_paper()` Parameters

All parameters from `generate()` plus:

| Parameter | Description |
|-----------|-------------|
| `paper_path` | Path to paper file (PDF or Markdown) |
| `methodology_api_key` | API key for extraction (overrides config) |
| `methodology_provider` | Provider for extraction (overrides config) |
| `methodology_model` | Model for extraction (overrides config) |
| `methodology_base_url` | Base URL for extraction (overrides config) |

## Result Object

The `GenerationResult` object contains:

| Attribute | Description |
|-----------|-------------|
| `success` | Whether generation was successful |
| `svg_path` | Path to generated SVG file |
| `mxgraph_path` | Path to generated mxGraph XML file |
| `preview_path` | Path to PNG preview image |
| `enhanced_path` | Path to first enhanced image |
| `enhanced_paths` | List of all enhanced image paths |
| `final_score` | Final quality score (0-10) |
| `iterations_used` | Number of iterations used |
| `methodology_text` | Extracted methodology (from paper) |
| `logs` | List of log messages |
| `error` | Error message if failed |

## Output Formats

- **SVG**: Scalable vector graphics, perfect for papers and presentations
- **mxGraph XML**: Compatible with draw.io/diagrams.net for further editing

## Enhancement Modes

| Mode | Description |
|------|-------------|
| `none` | Direct beautification without code reference |
| `code` | Use generated code (SVG/XML) as reference |
| `code2prompt` | Use LLM to analyze code and generate detailed prompt (recommended) |

## Dependencies

- Python 3.8+
- openai >= 1.0.0
- Pillow >= 9.0.0
- requests >= 2.25.0
- cairosvg >= 2.5.0

Optional:
- pymupdf, pdfplumber, or PyPDF2 (for PDF support)
- playwright (for mxGraph XML to PNG conversion)

## License

MIT License
