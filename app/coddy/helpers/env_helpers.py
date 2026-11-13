"""Environment variable loading and credentials normalization helper for Coddy."""

import logging
import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger(__name__)

DEFAULT_API_KEY: str = "dummy"


def _get_coddy_home_dir() -> Path:
    """Resolves the Coddy home directory (~/.coddy by default) without circular imports."""
    env_dir = os.getenv("CODDY_HOME")
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".coddy"


def normalize_credentials() -> None:
    """Normalizes credentials in environment variables.

    - Expands user home prefix (~) in GOOGLE_APPLICATION_CREDENTIALS so Google Cloud SDKs
      can locate service account key files.
    - Synchronizes GOOGLE_API_KEY and GEMINI_API_KEY so Google GenAI / Gemini clients work seamlessly.
    - Ensures a fallback OPENAI_API_KEY is present for local OpenAI-compatible inference servers.
    """
    # Expand user home prefix (~) in GOOGLE_APPLICATION_CREDENTIALS
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.expanduser(creds_path)

    # Synchronize GOOGLE_API_KEY and GEMINI_API_KEY
    google_key = os.getenv("GOOGLE_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    if google_key and not gemini_key:
        os.environ["GEMINI_API_KEY"] = google_key
    elif gemini_key and not google_key:
        os.environ["GOOGLE_API_KEY"] = gemini_key

    # Default fallback credentials for local OpenAI-compatible endpoints
    os.environ.setdefault("OPENAI_API_KEY", DEFAULT_API_KEY)


def load_environment(
    dotenv_path: str | Path | None = None,
    override: bool = False,
) -> list[Path]:
    """Loads environment variables from .env files and normalizes credentials.

    Search hierarchy:
    1. Explicit `dotenv_path` if provided.
    2. Local project `.env` found via `find_dotenv(usecwd=True)` (searches cwd and ancestor directories).
    3. Global `.env` in Coddy home directory (`~/.coddy/.env` or `$CODDY_HOME/.env`).

    Variables from local .env files take precedence over global ~/.coddy/.env defaults,
    while existing shell environment variables remain untouched unless `override=True`.

    Args:
        dotenv_path: Explicit path to a .env file to load.
        override: Whether variables from .env should override existing environment variables.

    Returns:
        List of Path objects for the .env files that were successfully loaded.
    """
    loaded_files: list[Path] = []

    if dotenv_path is not None:
        target = Path(dotenv_path).expanduser().resolve()
        if target.is_file():
            load_dotenv(dotenv_path=target, override=override)
            loaded_files.append(target)
            logger.debug("Loaded environment variables from explicit file: %s", target)
        else:
            logger.warning("Specified .env file does not exist: %s", target)
    else:
        # 1. Search for local .env starting from current working directory
        local_path_str = find_dotenv(usecwd=True)
        local_target: Path | None = None
        if local_path_str:
            candidate = Path(local_path_str).resolve()
            if candidate.is_file():
                local_target = candidate
                load_dotenv(dotenv_path=local_target, override=override)
                loaded_files.append(local_target)
                logger.debug("Loaded environment variables from local .env: %s", local_target)

        # 2. Check global Coddy home directory (~/.coddy/.env or $CODDY_HOME/.env)
        try:
            home_dir = _get_coddy_home_dir()
            global_target = (home_dir / ".env").resolve()
            if global_target.is_file():
                # Avoid loading twice if the local cwd is ~/.coddy
                if local_target is None or global_target != local_target:
                    # Global defaults should not override project-specific settings
                    load_dotenv(dotenv_path=global_target, override=False)
                    loaded_files.append(global_target)
                    logger.debug("Loaded environment variables from global .env: %s", global_target)
        except Exception as exc:
            logger.debug("Unable to check global Coddy home .env: %s", exc)

    # Normalize credentials across loaded environment
    normalize_credentials()

    return loaded_files


# Automatically initialize environment on module import
load_environment()
