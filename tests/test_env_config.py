"""Unit tests for environment configuration, python-dotenv support, and credentials normalization."""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from dotenv import dotenv_values

from app.coddy.helpers.env_helpers import (
    DEFAULT_API_KEY,
    load_environment,
    normalize_credentials,
)


def test_dotenv_dist_template_contains_credentials_variables():
    """Verify that .env.dist defines the expected Google AI Studio and Vertex AI configuration variables."""
    dist_path = Path(__file__).parent.parent / ".env.dist"
    assert dist_path.exists(), ".env.dist file should exist in the repository root"

    values = dotenv_values(dist_path)
    assert values.get("GOOGLE_CLOUD_PROJECT") == "My-Project"
    assert values.get("GOOGLE_CLOUD_LOCATION") == "global"
    assert values.get("GOOGLE_APPLICATION_CREDENTIALS") == "~/.config/gcloud/application_default_credentials.json"
    assert values.get("GOOGLE_API_KEY") == "GOOGLE_AI_STUDIO_API_KEY"
    assert "GOOGLE_GENAI_USE_VERTEXAI" in values


def test_google_application_credentials_tilde_expansion():
    """Verify that tilde in GOOGLE_APPLICATION_CREDENTIALS is expanded to user home path."""
    tilde_path = "~/.config/gcloud/application_default_credentials.json"
    expanded_path = os.path.expanduser(tilde_path)

    with patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": tilde_path}):
        normalize_credentials()
        assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == expanded_path
        assert not os.environ["GOOGLE_APPLICATION_CREDENTIALS"].startswith("~")


def test_normalize_credentials_syncs_google_and_gemini_api_key():
    """Verify that GOOGLE_API_KEY and GEMINI_API_KEY are synchronized when one is set."""
    # Test GOOGLE_API_KEY -> GEMINI_API_KEY
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key-123"}, clear=True):
        normalize_credentials()
        assert os.environ.get("GEMINI_API_KEY") == "test-key-123"

    # Test GEMINI_API_KEY -> GOOGLE_API_KEY
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-gemini-456"}, clear=True):
        normalize_credentials()
        assert os.environ.get("GOOGLE_API_KEY") == "test-gemini-456"


def test_normalize_credentials_openai_fallback():
    """Verify default fallback OPENAI_API_KEY is injected if unset."""
    with patch.dict(os.environ, {}, clear=True):
        normalize_credentials()
        assert os.environ.get("OPENAI_API_KEY") == DEFAULT_API_KEY


def test_load_environment_explicit_file(tmp_path):
    """Verify load_environment loads variables from an explicitly provided .env file."""
    custom_env = tmp_path / "custom.env"
    custom_env.write_text("CUSTOM_VAR_FOO=bar123\n")

    with patch.dict(os.environ, {}, clear=True):
        loaded = load_environment(dotenv_path=custom_env)
        assert custom_env in loaded
        assert os.environ.get("CUSTOM_VAR_FOO") == "bar123"


def test_load_environment_hierarchy_local_overrides_global(tmp_path, monkeypatch):
    """Verify local project .env overrides global ~/.coddy/.env defaults."""
    global_dir = tmp_path / "global_coddy"
    global_dir.mkdir()
    global_env = global_dir / ".env"
    global_env.write_text("SHARED_CONFIG=from_global\nGLOBAL_ONLY=only_in_global\n")

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    local_env = project_dir / ".env"
    local_env.write_text("SHARED_CONFIG=from_local\nLOCAL_ONLY=only_in_local\n")

    monkeypatch.setenv("CODDY_HOME", str(global_dir))
    monkeypatch.chdir(project_dir)

    with patch.dict(os.environ, {"CODDY_HOME": str(global_dir)}, clear=True):
        loaded = load_environment()
        assert local_env.resolve() in [f.resolve() for f in loaded]
        assert global_env.resolve() in [f.resolve() for f in loaded]

        assert os.environ.get("SHARED_CONFIG") == "from_local"
        assert os.environ.get("LOCAL_ONLY") == "only_in_local"
        assert os.environ.get("GLOBAL_ONLY") == "only_in_global"


def test_load_environment_shell_precedence(tmp_path, monkeypatch):
    """Verify existing shell environment variables are preserved over .env when override=False."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    local_env = project_dir / ".env"
    local_env.write_text("PRESET_VAR=from_file\n")

    monkeypatch.chdir(project_dir)

    with patch.dict(os.environ, {"PRESET_VAR": "from_shell"}):
        load_environment(dotenv_path=local_env, override=False)
        assert os.environ.get("PRESET_VAR") == "from_shell"

    with patch.dict(os.environ, {"PRESET_VAR": "from_shell"}):
        load_environment(dotenv_path=local_env, override=True)
        assert os.environ.get("PRESET_VAR") == "from_file"


def test_load_environment_nonexistent_file():
    """Verify loading a nonexistent file degrades gracefully without raising."""
    nonexistent = Path("/path/to/nonexistent/never_exists.env")
    loaded = load_environment(dotenv_path=nonexistent)
    assert loaded == []


def test_env_file_ignored_by_git():
    """Verify that .env is ignored and .env.dist is not ignored by git."""
    check_env = subprocess.run(
        ["git", "check-ignore", "-q", ".env"],
        cwd=Path(__file__).parent.parent,
    )
    assert check_env.returncode == 0, ".env must be ignored by git"

    check_dist = subprocess.run(
        ["git", "check-ignore", "-q", ".env.dist"],
        cwd=Path(__file__).parent.parent,
    )
    assert check_dist.returncode == 1, ".env.dist must NOT be ignored by git"
