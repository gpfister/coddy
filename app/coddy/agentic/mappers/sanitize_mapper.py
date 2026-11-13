"""Deterministic Markdown mapper for SanitizedUserRequest structured output."""

from app.coddy.agentic.schemas.sanitize import SanitizedUserRequest


class SanitizeMapper:
    """Transforms a SanitizedUserRequest structured instance into human-readable Markdown."""

    @staticmethod
    def format_user_request(result: SanitizedUserRequest) -> str:
        """Formats the user request and ambiguous terms into Markdown."""
        parts: list[str] = [
            "## User request",
            "",
            result.user_request.strip(),
        ]
        if result.ambiguous_terms:
            parts.extend(["", "## Ambiguous terms", ""])
            term_blocks: list[str] = []
            for idx, item in enumerate(result.ambiguous_terms, start=1):
                block = [f'{idx}. "{item.term}" could mean:']
                for meaning in item.meanings:
                    clean_meaning = meaning.strip().rstrip(".")
                    block.append(f"  - {clean_meaning}.")
                term_blocks.append("\n".join(block))
            parts.append("\n\n".join(term_blocks))
        return "\n".join(parts)

    @staticmethod
    def format_local_project_instructions(result: SanitizedUserRequest) -> str:
        """Formats the sanitized local project instructions into Markdown."""
        instructions = result.local_project_instructions
        if not instructions or not instructions.strip():
            return ""
        return f"## Sanitized local project instructions\n\n{instructions.strip()}"

    @staticmethod
    def format_local_project_description(result: SanitizedUserRequest) -> str:
        """Formats the sanitized local project description into Markdown."""
        description = result.local_project_description
        if not description or not description.strip():
            return ""
        return f"## Sanitized local project description\n\n{description.strip()}"
