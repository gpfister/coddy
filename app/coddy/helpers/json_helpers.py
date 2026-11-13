"""JSON extraction and reasoning utilities."""

import re
from pathlib import Path


def extract_reasoning(text: str) -> str | None:
    """Extracts content inside <think>...</think> tags if present."""
    match = re.search(r"<think>([\s\S]*?)</think>", text)
    if match:
        return match.group(1).strip()
    return None


def extract_json_payload(text: str) -> str:
    """Extracts clean JSON substring from model response, stripping think tags and code fences."""
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.DOTALL).strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    json_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
    if json_match:
        return json_match.group(0)
    return cleaned


def find_agents_markdown() -> Path | None:
    """Finds local project instructions (AGENTS.md) in current directory, repo root, or parent hierarchy."""
    cwd = Path.cwd()
    candidate = cwd / "AGENTS.md"
    if candidate.is_file():
        return candidate

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "AGENTS.md"
        if candidate.is_file():
            return candidate

    return None


def find_skills_directory() -> Path | None:
    """Finds local .agents/skills directory in current directory, repo root, or parent hierarchy."""
    cwd = Path.cwd()
    candidate = cwd / ".agents" / "skills"
    if candidate.is_dir():
        return candidate

    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".agents" / "skills"
        if candidate.is_dir():
            return candidate

    return None


def get_local_skills_summary(skills_dir: Path) -> str:
    """Builds a formatted reference summary of all available local skills in .agents/skills."""
    summary_parts = ["## Available Local Agent Skills (.agents/skills)"]
    skill_mds = sorted(skills_dir.glob("*/SKILL.md"))
    if not skill_mds:
        return ""
    for skill_file in skill_mds:
        skill_name = skill_file.parent.name
        try:
            content = skill_file.read_text(encoding="utf-8").strip()
            summary_parts.append(f"### Skill: {skill_name}\nPath: `{skill_file}`\n\n{content}")
        except Exception:
            continue
    return "\n\n".join(summary_parts)
