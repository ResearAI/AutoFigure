"""
API endpoint and protocol helpers.

Provider names are UI presets or legacy compatibility labels. The protocol is
what determines the request shape.
"""

import base64
import io
from typing import Any, Dict, List, Optional

import requests
from PIL import Image


OPENAI_COMPATIBLE = "openai-compatible"
GEMINI_NATIVE = "gemini-native"


def normalize_protocol(provider: Optional[str] = None, protocol: Optional[str] = None) -> str:
    """Return the effective API protocol for a provider/config pair."""
    if protocol:
        value = protocol.strip().lower().replace("_", "-")
        if value in {"openai", "openai-compatible", "openai-compatible-chat"}:
            return OPENAI_COMPATIBLE
        if value in {"gemini", "gemini-native", "google-gemini"}:
            return GEMINI_NATIVE

    provider_value = (provider or "").strip().lower().replace("_", "-")
    if provider_value in {"gemini", "google-gemini"}:
        return GEMINI_NATIVE
    return OPENAI_COMPATIBLE


def default_base_url(provider: Optional[str], protocol: Optional[str] = None) -> str:
    """Default base URL for presets. User-supplied base_url should override this."""
    provider_value = (provider or "").strip().lower().replace("_", "-")
    effective_protocol = normalize_protocol(provider_value, protocol)

    if provider_value == "openrouter":
        return "https://openrouter.ai/api/v1"
    if provider_value == "bianxie":
        return "https://api.bianxie.ai/v1"
    if effective_protocol == GEMINI_NATIVE:
        return "https://generativelanguage.googleapis.com/v1beta"
    if provider_value in {"gemini", "google-gemini"}:
        return "https://generativelanguage.googleapis.com/v1beta/openai/"
    return ""


def normalize_openai_base_url(base_url: str) -> str:
    """Normalize an OpenAI-compatible base URL for SDK clients."""
    value = (base_url or "").strip().rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    return value


def chat_completions_url(base_url: str) -> str:
    """Return a direct /chat/completions URL for requests-based calls."""
    value = normalize_openai_base_url(base_url)
    if not value:
        return value
    return f"{value}/chat/completions"


def normalize_gemini_base_url(base_url: str) -> str:
    """Normalize a Gemini native base URL before adding /models/...:generateContent."""
    value = (base_url or "").strip().split("?", 1)[0].rstrip("/")

    model_marker = "/models/"
    if model_marker in value:
        value = value.split(model_marker, 1)[0].rstrip("/")

    for suffix in ("/chat/completions", "/completions", "/v1/chat", "/openai"):
        if value.endswith(suffix):
            value = value[: -len(suffix)].rstrip("/")

    if value.endswith("/models"):
        value = value[: -len("/models")].rstrip("/")

    if "generativelanguage.googleapis.com" in value and "/v1beta" not in value:
        value = f"{value}/v1beta"
    elif value.endswith("/gemini") and "/v1beta" not in value:
        value = f"{value}/v1beta"

    return value


def build_gemini_parts(contents: List[Any]) -> List[Dict[str, Any]]:
    """Convert text/PIL content parts into Gemini native request parts."""
    parts: List[Dict[str, Any]] = []
    for part in contents:
        if isinstance(part, str):
            parts.append({"text": part})
        elif isinstance(part, Image.Image):
            buf = io.BytesIO()
            part.save(buf, format="PNG")
            image_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            parts.append({
                "inlineData": {
                    "mimeType": "image/png",
                    "data": image_b64,
                }
            })
        else:
            print(f"[APIProtocol] Skipping unsupported content type: {type(part)}")
    return parts


def call_gemini_native_text(
    contents: List[Any],
    api_key: str,
    model: str,
    base_url: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
) -> Optional[str]:
    """Call Gemini native generateContent and return text from the first candidate."""
    if not api_key:
        print("[GeminiNative] ERROR: API key not provided!")
        return None
    if not model:
        print("[GeminiNative] ERROR: Model not specified!")
        return None
    if not base_url:
        print("[GeminiNative] ERROR: Base URL not specified!")
        return None

    api_url = f"{normalize_gemini_base_url(base_url)}/models/{model}:generateContent?key={api_key}"
    print(f"[GeminiNative] API URL: {api_url.split('?key=', 1)[0]}?key=***")
    payload: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": build_gemini_parts(contents)}],
        "generationConfig": {"temperature": temperature},
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    if max_tokens:
        payload["generationConfig"]["maxOutputTokens"] = max_tokens

    response = requests.post(
        api_url,
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=300,
    )
    if response.status_code != 200:
        raise Exception(f"Gemini native API request failed: {response.status_code} - {response.text[:500]}")

    result = response.json()
    if "error" in result:
        error_msg = result.get("error", {})
        if isinstance(error_msg, dict):
            error_msg = error_msg.get("message", str(error_msg))
        raise Exception(f"Gemini native API error: {error_msg}")

    text_parts: List[str] = []
    for candidate in result.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            if "text" in part:
                text_parts.append(part["text"])

    return "\n".join(text_parts).strip() or None
