"""Tests for Endpoint and Model Verification."""

import httpx
import pytest

from app.coddy.helpers.pre_flight_checks import (
    LOCAL_ENDPOINT_URL,
    get_available_models,
    resolve_model_id,
    verify_models,
)


def test_endpoint_constant():
    """Verify default local endpoint URL."""
    assert LOCAL_ENDPOINT_URL == "http://localhost:1234/v1"


def test_get_available_models_success(monkeypatch):
    """Verify fetching models from endpoint."""

    class MockResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": [
                    {"id": "google/gemma-4-e4b"},
                    {"id": "google/gemma-4-31b"},
                ]
            }

    called_url = []

    def mock_get(self, url):
        called_url.append(url)
        return MockResponse()

    monkeypatch.setattr(httpx.Client, "get", mock_get)
    models = get_available_models()
    assert models == ["google/gemma-4-e4b", "google/gemma-4-31b"]
    assert called_url == ["http://localhost:1234/v1/models"]


def test_get_available_models_connection_error(monkeypatch):
    """Verify connection error handling."""

    def mock_get(self, url):
        raise httpx.ConnectError("Failed to connect")

    monkeypatch.setattr(httpx.Client, "get", mock_get)
    with pytest.raises(ConnectionError) as exc_info:
        get_available_models()
    assert "Could not connect to local LLM server" in str(exc_info.value)


def test_verify_models_strict_matching_all_present(monkeypatch):
    """Verify matching when all requested models are present."""
    monkeypatch.setattr(
        "app.coddy.helpers.pre_flight_checks.get_available_models",
        lambda endpoint=LOCAL_ENDPOINT_URL: [
            "google/gemma-4-e4b",
            "google/gemma-4-31b",
            "google/gemma-4-26b-a4b",
        ],
    )
    ok, missing, err_msg = verify_models(["google/gemma-4-e4b", "google/gemma-4-31b"])
    assert ok is True
    assert missing == []
    assert err_msg is None


def test_verify_models_strict_matching_missing(monkeypatch):
    """Verify detection of missing models."""
    monkeypatch.setattr(
        "app.coddy.helpers.pre_flight_checks.get_available_models",
        lambda endpoint=LOCAL_ENDPOINT_URL: ["google/gemma-4-e4b"],
    )
    ok, missing, err_msg = verify_models(["google/gemma-4-e4b", "google/gemma-4-31b", "google/gemma-4-26b-a4b"])
    assert ok is False
    assert missing == ["google/gemma-4-31b", "google/gemma-4-26b-a4b"]
    assert "The following required model(s) are missing from local LLM" in err_msg
    assert "google/gemma-4-31b" in err_msg
    assert "google/gemma-4-26b-a4b" in err_msg


def test_verify_models_strict_matching_rejects_fuzzy_alias(monkeypatch):
    """Strict matching does NOT treat google/gemma-4-26b-e24 as equal to google/gemma-4-26b-a4b."""
    monkeypatch.setattr(
        "app.coddy.helpers.pre_flight_checks.get_available_models",
        lambda endpoint=LOCAL_ENDPOINT_URL: ["google/gemma-4-26b-e24"],
    )
    ok, missing, err_msg = verify_models(["google/gemma-4-26b-a4b"])
    assert ok is False
    assert missing == ["google/gemma-4-26b-a4b"]


def test_resolve_model_id_exact_and_variants():
    """Verify resolution of exact and quantization variants."""
    available = [
        "google/gemma-4-e4b",
        "google/gemma-4-31b",
        "google/gemma-4-26b-a4b-qat",
        "text-embedding-nomic-embed-text-v1.5@q8_0",
    ]

    # Exact match
    assert resolve_model_id("google/gemma-4-e4b", available) == "google/gemma-4-e4b"
    assert resolve_model_id("google/gemma-4-31b", available) == "google/gemma-4-31b"

    # Quantization variant match (-qat)
    assert resolve_model_id("google/gemma-4-26b-a4b", available) == "google/gemma-4-26b-a4b-qat"

    # Quantization variant match (@q8_0)
    assert (
        resolve_model_id("text-embedding-nomic-embed-text-v1.5", available)
        == "text-embedding-nomic-embed-text-v1.5@q8_0"
    )

    # Architecture mismatch is rejected
    assert resolve_model_id("google/gemma-4-26b-e24", available) is None
    assert resolve_model_id("google/gemma-4-12b", available) is None


def test_verify_models_resolves_quantization_variant(monkeypatch):
    """Verify quantization variant resolution in verify_models."""
    monkeypatch.setattr(
        "app.coddy.helpers.pre_flight_checks.get_available_models",
        lambda endpoint=LOCAL_ENDPOINT_URL: [
            "google/gemma-4-e4b",
            "google/gemma-4-31b",
            "google/gemma-4-26b-a4b-qat",
        ],
    )
    res = verify_models(["google/gemma-4-e4b", "google/gemma-4-31b", "google/gemma-4-26b-a4b"])
    ok, missing, err_msg = res
    assert ok is True
    assert missing == []
    assert err_msg is None
    assert res.resolved_models["google/gemma-4-26b-a4b"] == "google/gemma-4-26b-a4b-qat"
