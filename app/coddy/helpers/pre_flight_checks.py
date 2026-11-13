"""Endpoint and model verification utility for Coddy.

Ensures that required local models are available on the local OpenAI-compatible endpoint
(strictly fixed to http://localhost:1234/v1).
"""

import os

import httpx

from app.coddy.helpers.env_helpers import load_environment

load_environment()

LOCAL_ENDPOINT_URL: str = "http://localhost:1234/v1"
DEFAULT_API_KEY: str = os.getenv("OPENAI_API_KEY", "dummy")

VALID_VARIANT_PREFIXES: tuple[str, ...] = (
    "-qat",
    "@",
    "-gguf",
    "-GGUF",
    "-q",
    ".q",
    "-int",
    "-fp16",
    "-bf16",
    "-it",
    "-instruct",
)


def resolve_model_id(required_model: str, available_models: list[str]) -> str | None:
    """Resolves a required model ID against available local models.

    Prefers an exact match. If not present, resolves to a compatible quantization
    or variant suffix (e.g. `-qat`, `@q4_k_m`, `-gguf`), while strictly rejecting
    mismatched base architectures (e.g. `-e24` vs `-a4b`).

    Args:
        required_model: The required canonical model identifier.
        available_models: List of model identifiers currently loaded on local LLM.

    Returns:
        The matching available model identifier, or None if no compatible model is found.
    """
    clean_req = required_model
    clean_req = clean_req.removeprefix("openai/")

    cleaned_available: dict[str, str] = {}
    for cand in available_models:
        c = cand
        c = c.removeprefix("openai/")
        cleaned_available[c] = cand

    if clean_req in cleaned_available:
        return cleaned_available[clean_req]

    req_lower = clean_req.lower()
    for cand_clean, original in cleaned_available.items():
        cand_lower = cand_clean.lower()
        if cand_lower.startswith(req_lower):
            suffix = cand_lower[len(req_lower) :]
            if any(suffix.startswith(prefix.lower()) for prefix in VALID_VARIANT_PREFIXES):
                return original

    # If required_model itself has a variant suffix, check against base and other variants
    base_req = req_lower
    for prefix in VALID_VARIANT_PREFIXES:
        p_clean = prefix.lower()
        if p_clean in base_req:
            base_req = base_req.split(p_clean)[0]
            break

    if base_req != req_lower:
        for cand_clean, original in cleaned_available.items():
            cand_lower = cand_clean.lower()
            if cand_lower == base_req:
                return original
            if cand_lower.startswith(base_req):
                suffix = cand_lower[len(base_req) :]
                if any(suffix.startswith(prefix.lower()) for prefix in VALID_VARIANT_PREFIXES):
                    return original

    return None


class ModelVerificationResult(tuple):
    """Result of model verification: (is_valid, missing_models, error_message).

    Subclasses tuple for backward compatibility with 3-tuple unpacking:
    `is_valid, missing, error_msg = verify_models(...)`
    while also exposing `resolved_models: Dict[str, str]`.
    """

    is_valid: bool
    missing_models: list[str]
    error_message: str | None
    resolved_models: dict[str, str]

    def __new__(
        cls,
        is_valid: bool,
        missing_models: list[str],
        error_message: str | None,
        resolved_models: dict[str, str] | None = None,
    ):
        return super().__new__(cls, (is_valid, missing_models, error_message))

    def __init__(
        self,
        is_valid: bool,
        missing_models: list[str],
        error_message: str | None,
        resolved_models: dict[str, str] | None = None,
    ):
        self.is_valid = is_valid
        self.missing_models = missing_models
        self.error_message = error_message
        self.resolved_models = resolved_models or {}


def get_available_models(endpoint: str = LOCAL_ENDPOINT_URL) -> list[str]:
    """Queries the local LLM server for the list of available model IDs.

    Args:
        endpoint: Local endpoint URL (defaults to http://localhost:1234/v1).

    Returns:
        List of available model IDs.

    Raises:
        ConnectionError: If connection to the endpoint fails.
    """
    base = endpoint.rstrip("/")
    url = f"{base}/models"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return [item["id"] for item in data.get("data", []) if "id" in item]
    except Exception as e:
        raise ConnectionError(f"Could not connect to local LLM server at '{base}': {e}") from e


def check_model_availability(url: str, model: str) -> bool:
    """Checks whether a specific model (or compatible variant) is available at the endpoint.

    Args:
        url: Endpoint base URL (e.g. http://localhost:1234/v1).
        model: Canonical model name (e.g. 'google/gemma-4-12b' or 'openai/google/gemma-4-12b').

    Returns:
        True if the model or a compatible variant is available, False otherwise.
    """
    try:
        available = get_available_models(url)
        return resolve_model_id(model, available) is not None
    except Exception:
        return False


def verify_models(
    required_models: list[str],
    endpoint: str = LOCAL_ENDPOINT_URL,
) -> ModelVerificationResult:
    """Verifies that all required models are present on the local LLM server.

    Checks for exact model matches or compatible quantization variants.

    Args:
        required_models: List of required model identifiers.
        endpoint: Local endpoint URL (defaults to http://localhost:1234/v1).

    Returns:
        ModelVerificationResult tuple of (is_valid, missing_models, error_message)
        with `.resolved_models` mapping required model IDs to available model IDs.
    """
    base = endpoint.rstrip("/")
    try:
        available = get_available_models(base)
    except Exception as e:
        return ModelVerificationResult(
            False,
            required_models,
            f"Could not connect to local LLM server at '{base}'. "
            f"Please ensure your local LLM server (e.g. LM Studio) is running.\nDetails: {e}",
            {},
        )

    resolved: dict[str, str] = {}
    missing: list[str] = []

    for req in required_models:
        match = resolve_model_id(req, available)
        if match is not None:
            resolved[req] = match
        else:
            missing.append(req)

    if missing:
        available_str = ", ".join(f"'{m}'" for m in available) if available else "none"
        missing_str = ", ".join(f"'{m}'" for m in missing)
        error_msg = (
            f"The following required model(s) are missing from local LLM server ({base}): {missing_str}.\n"
            f"Currently loaded models: [{available_str}].\n"
            f"Please load the required model(s) in your local LLM server before running Coddy."
        )
        return ModelVerificationResult(False, missing, error_msg, resolved)

    return ModelVerificationResult(True, [], None, resolved)
