"""
AutoFigure SDK Configuration Module

Provides configuration management for LLM providers, image enhancement,
and other SDK settings.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path
import os


@dataclass
class Config:
    """
    Configuration for AutoFigure SDK.

    Attributes:
        generation_api_key: API key for figure generation LLM
        generation_base_url: Base URL for generation API (optional)
        generation_model: Model name for generation (optional)

        methodology_api_key: API key for methodology extraction (defaults to generation_api_key)
        methodology_base_url: Base URL for methodology API (optional)
        methodology_model: Model name for methodology extraction (optional)

        enhancement_api_key: API key for image enhancement (optional)
        enhancement_provider: Enhancement provider ('replicate', 'stability', 'local')

        max_iterations: Maximum iteration count for refinement
        quality_threshold: Quality score threshold (0-10) to stop iteration
        output_dir: Output directory for generated files
    """

    # Generation LLM settings
    generation_api_key: str = ""
    generation_base_url: Optional[str] = None
    generation_model: Optional[str] = None
    generation_provider: str = "openrouter"  # openrouter, requesty, bianxie, gemini

    # Methodology extraction LLM settings (defaults to generation settings)
    methodology_api_key: Optional[str] = None
    methodology_base_url: Optional[str] = None
    methodology_model: Optional[str] = None
    methodology_provider: Optional[str] = None

    # Image enhancement settings
    enhancement_api_key: Optional[str] = None
    enhancement_provider: str = "openrouter"  # openrouter, requesty, bianxie, gemini
    enhancement_model: Optional[str] = None
    enhancement_base_url: Optional[str] = None
    enhancement_input_type: str = "code2prompt"  # none, code, code2prompt
    enhancement_count: int = 1  # Number of enhanced image variants to generate
    art_style: str = ""  # Art style for enhancement

    # Pipeline settings
    max_iterations: int = 5
    quality_threshold: float = 9.0
    min_improvement: float = 0.2
    output_dir: str = "./autofigure_output"

    # Reference figures
    custom_references: Optional[List[str]] = None

    def __post_init__(self):
        """Initialize default values after dataclass creation."""
        # Default methodology settings to generation settings
        if self.methodology_api_key is None:
            self.methodology_api_key = self.generation_api_key
        if self.methodology_base_url is None:
            self.methodology_base_url = self.generation_base_url
        if self.methodology_model is None:
            self.methodology_model = self.generation_model
        if self.methodology_provider is None:
            self.methodology_provider = self.generation_provider

        # Set default base URLs based on provider
        if self.generation_base_url is None:
            self.generation_base_url = self._get_default_base_url(self.generation_provider)
        if self.methodology_base_url is None:
            self.methodology_base_url = self._get_default_base_url(self.methodology_provider)

        # Set default models
        if self.generation_model is None:
            self.generation_model = self._get_default_model(self.generation_provider)
        if self.methodology_model is None:
            self.methodology_model = self._get_default_model(self.methodology_provider)

        # Set default enhancement settings
        if self.enhancement_model is None:
            self.enhancement_model = self._get_default_enhancement_model(self.enhancement_provider)
        if self.enhancement_base_url is None:
            self.enhancement_base_url = self._get_default_base_url(self.enhancement_provider)

    def _get_default_base_url(self, provider: str) -> str:
        """Get default base URL for a provider."""
        urls = {
            "openrouter": "https://openrouter.ai/api/v1",
            "requesty": "https://router.requesty.ai/v1",
            "bianxie": "https://api.bianxie.ai/v1",
            "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
        }
        return urls.get(provider, "https://openrouter.ai/api/v1")

    def _get_default_model(self, provider: str) -> str:
        """Get default model for a provider."""
        models = {
            "openrouter": "google/gemini-3.1-pro-preview",
            "requesty": "openai/gpt-4o-mini",
            "bianxie": "gemini-3.1-pro-preview",
            "gemini": "gemini-3.1-pro-preview",
        }
        return models.get(provider, "google/gemini-3.1-pro-preview")

    def _get_default_enhancement_model(self, provider: str) -> str:
        """Get default enhancement model for a provider."""
        models = {
            "openrouter": "google/gemini-3.1-flash-image-preview",
            "requesty": "google/gemini-3.1-flash-image-preview",
            "bianxie": "gemini-3.1-flash-image-preview",
            "gemini": "gemini-3.1-flash-image-preview",
        }
        return models.get(provider, "google/gemini-3.1-flash-image-preview")

    def get_references(self) -> List[str]:
        """
        Get reference figure paths.
        Returns custom references if provided, otherwise returns built-in defaults.
        """
        if self.custom_references:
            return self.custom_references

        # Return built-in reference figures
        sdk_dir = Path(__file__).parent
        ref_dir = sdk_dir / "references" / "paper"

        if ref_dir.exists():
            refs = sorted(ref_dir.glob("*.png"))
            return [str(r) for r in refs]

        return []

    def validate(self) -> List[str]:
        """
        Validate configuration and return list of errors.
        Returns empty list if configuration is valid.
        """
        errors = []

        if not self.generation_api_key:
            errors.append("generation_api_key is required")

        if self.max_iterations < 1:
            errors.append("max_iterations must be at least 1")

        if not (0 <= self.quality_threshold <= 10):
            errors.append("quality_threshold must be between 0 and 10")

        return errors

    @classmethod
    def from_env(cls) -> "Config":
        """
        Create Config from environment variables.

        Environment variables:
            AUTOFIGURE_API_KEY: Main API key for generation
            AUTOFIGURE_BASE_URL: Base URL for API
            AUTOFIGURE_MODEL: Model name
            AUTOFIGURE_PROVIDER: Provider name (openrouter, requesty, bianxie, gemini)
            AUTOFIGURE_METHODOLOGY_API_KEY: API key for methodology extraction
            AUTOFIGURE_ENHANCEMENT_API_KEY: API key for image enhancement
            AUTOFIGURE_ENHANCEMENT_PROVIDER: Enhancement provider (openrouter, requesty, bianxie, gemini)
            AUTOFIGURE_ENHANCEMENT_MODEL: Enhancement model name
            AUTOFIGURE_ENHANCEMENT_BASE_URL: Enhancement API base URL
            AUTOFIGURE_ENHANCEMENT_INPUT_TYPE: Enhancement input type (none, code, code2prompt)
            AUTOFIGURE_ART_STYLE: Art style for enhancement
            AUTOFIGURE_MAX_ITERATIONS: Maximum iterations
            AUTOFIGURE_QUALITY_THRESHOLD: Quality threshold
            AUTOFIGURE_OUTPUT_DIR: Output directory
        """
        return cls(
            generation_api_key=os.environ.get("AUTOFIGURE_API_KEY", ""),
            generation_base_url=os.environ.get("AUTOFIGURE_BASE_URL"),
            generation_model=os.environ.get("AUTOFIGURE_MODEL"),
            generation_provider=os.environ.get("AUTOFIGURE_PROVIDER", "openrouter"),
            methodology_api_key=os.environ.get("AUTOFIGURE_METHODOLOGY_API_KEY"),
            enhancement_api_key=os.environ.get("AUTOFIGURE_ENHANCEMENT_API_KEY"),
            enhancement_provider=os.environ.get("AUTOFIGURE_ENHANCEMENT_PROVIDER", "openrouter"),
            enhancement_model=os.environ.get("AUTOFIGURE_ENHANCEMENT_MODEL"),
            enhancement_base_url=os.environ.get("AUTOFIGURE_ENHANCEMENT_BASE_URL"),
            enhancement_input_type=os.environ.get("AUTOFIGURE_ENHANCEMENT_INPUT_TYPE", "code2prompt"),
            art_style=os.environ.get("AUTOFIGURE_ART_STYLE", ""),
            max_iterations=int(os.environ.get("AUTOFIGURE_MAX_ITERATIONS", "5")),
            quality_threshold=float(os.environ.get("AUTOFIGURE_QUALITY_THRESHOLD", "9.0")),
            output_dir=os.environ.get("AUTOFIGURE_OUTPUT_DIR", "./autofigure_output"),
        )
