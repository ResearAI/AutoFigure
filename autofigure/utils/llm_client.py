"""
Unified LLM Client for AutoFigure SDK.

Provides a consistent interface for calling various LLM providers
(OpenRouter, Bianxie, Gemini, etc.)
"""

import base64
import io
from typing import Any, Dict, List, Optional, Union

from PIL import Image

from .api_protocol import (
    GEMINI_NATIVE,
    OPENAI_COMPATIBLE,
    call_gemini_native_text,
    default_base_url,
    normalize_openai_base_url,
    normalize_protocol,
)


class LLMClient:
    """
    Unified LLM client supporting multiple providers.

    Supports OpenAI-compatible APIs including:
    - OpenRouter
    - Bianxie
    - Google Gemini (via OpenAI-compatible endpoint)
    - Any OpenAI-compatible endpoint
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "google/gemini-3.1-pro-preview",
        provider: str = "openrouter",
        protocol: Optional[str] = None,
    ):
        """
        Initialize LLM client.

        Args:
            api_key: API key for the provider
            base_url: Base URL for the API endpoint
            model: Model name to use
            provider: Provider name/preset (openrouter, bianxie, gemini, custom)
            protocol: API protocol (openai-compatible, gemini-native)
        """
        self.api_key = api_key
        self.protocol = normalize_protocol(provider, protocol)
        self.base_url = base_url or default_base_url(provider, self.protocol)
        self.model = model
        self.provider = provider

        if self.protocol == OPENAI_COMPATIBLE:
            self.base_url = normalize_openai_base_url(self.base_url)

    def call(
        self,
        contents: List[Any],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Optional[str]:
        """
        Call the LLM with text and optional images.

        Args:
            contents: List of content items (strings or PIL Images)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            Response text, or None on failure
        """
        try:
            if not self.api_key:
                print("[LLMClient] ERROR: API key not provided!")
                return None

            if self.protocol == GEMINI_NATIVE:
                return call_gemini_native_text(
                    contents=contents,
                    api_key=self.api_key,
                    model=self.model,
                    base_url=self.base_url,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

            from openai import OpenAI

            client = OpenAI(base_url=self.base_url, api_key=self.api_key)

            # Build message content
            message_content: List[Dict[str, Any]] = []
            for part in contents:
                if isinstance(part, str):
                    message_content.append({"type": "text", "text": part})
                elif isinstance(part, Image.Image):
                    # Convert PIL Image to base64
                    buf = io.BytesIO()
                    part.save(buf, format="PNG")
                    image_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    message_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"}
                    })
                else:
                    print(f"[LLMClient] Skipping unsupported content type: {type(part)}")

            # Build request kwargs
            kwargs = {
                "model": self.model,
                "messages": [{"role": "user", "content": message_content}],
                "temperature": temperature,
            }
            if max_tokens:
                kwargs["max_tokens"] = max_tokens

            completion = client.chat.completions.create(**kwargs)

            if completion and completion.choices:
                return completion.choices[0].message.content
            return None

        except Exception as e:
            print(f"[LLMClient] API call failed: {e}")
            return None

    def call_with_system(
        self,
        system_prompt: str,
        user_contents: List[Any],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Optional[str]:
        """
        Call the LLM with a system prompt and user message.

        Args:
            system_prompt: System message
            user_contents: List of user content items
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            Response text, or None on failure
        """
        try:
            if not self.api_key:
                print("[LLMClient] ERROR: API key not provided!")
                return None

            if self.protocol == GEMINI_NATIVE:
                return call_gemini_native_text(
                    contents=user_contents,
                    api_key=self.api_key,
                    model=self.model,
                    base_url=self.base_url,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

            from openai import OpenAI

            client = OpenAI(base_url=self.base_url, api_key=self.api_key)

            # Build user message content
            user_content: List[Dict[str, Any]] = []
            for part in user_contents:
                if isinstance(part, str):
                    user_content.append({"type": "text", "text": part})
                elif isinstance(part, Image.Image):
                    buf = io.BytesIO()
                    part.save(buf, format="PNG")
                    image_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"}
                    })

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens:
                kwargs["max_tokens"] = max_tokens

            completion = client.chat.completions.create(**kwargs)

            if completion and completion.choices:
                return completion.choices[0].message.content
            return None

        except Exception as e:
            print(f"[LLMClient] API call with system prompt failed: {e}")
            return None


def create_client_from_config(config: "Config", purpose: str = "generation") -> LLMClient:
    """
    Create an LLM client from SDK config.

    Args:
        config: AutoFigure SDK Config object
        purpose: 'generation' or 'methodology'

    Returns:
        Configured LLMClient instance
    """
    if purpose == "methodology":
        return LLMClient(
            api_key=config.methodology_api_key,
            base_url=config.methodology_base_url,
            model=config.methodology_model,
            provider=config.methodology_provider,
            protocol=config.methodology_protocol,
        )
    else:
        return LLMClient(
            api_key=config.generation_api_key,
            base_url=config.generation_base_url,
            model=config.generation_model,
            provider=config.generation_provider,
            protocol=config.generation_protocol,
        )
