"""Deterministic Markdown mapper for EnhancedUserRequest structured output."""

from app.coddy.agentic.schemas.enhanced_user_request import EnhancedUserRequest


class EnhancedUserRequestMapper:
    """Transforms an EnhancedUserRequest structured instance into human-readable Markdown."""

    @staticmethod
    def to_markdown(result: EnhancedUserRequest) -> str:
        """Formats the enhanced user request and clarification log into Markdown."""
        parts: list[str] = [
            "## Enhanced User Request",
            "",
            result.user_request.strip(),
        ]

        if result.clarifications:
            parts.extend(["", "## Clarifications & Resolved Ambiguities", ""])
            clarification_blocks: list[str] = []
            for idx, item in enumerate(result.clarifications, start=1):
                block = [f"### Clarification {idx}"]
                if item.ambiguity_term:
                    block.append(f"**Ambiguity Term**: `{item.ambiguity_term}`")
                block.append(f"**Question**: {item.question.strip()}")
                block.append(f"**Answer**: {item.answer.strip()}")
                if item.rationale and item.rationale.strip():
                    block.append(f"**Rationale**: {item.rationale.strip()}")
                clarification_blocks.append("\n\n".join(block))
            parts.append("\n\n---\n\n".join(clarification_blocks))

        return "\n".join(parts)

    @staticmethod
    def format_local_project_instructions(result: EnhancedUserRequest) -> str:
        """Formats the local project instructions into Markdown."""
        instructions = result.local_project_instructions
        if not instructions or not instructions.strip():
            return ""
        return f"## Sanitized local project instructions\n\n{instructions.strip()}"

    @staticmethod
    def format_local_project_description(result: EnhancedUserRequest) -> str:
        """Formats the local project description into Markdown."""
        description = result.local_project_description
        if not description or not description.strip():
            return ""
        return f"## Sanitized local project description\n\n{description.strip()}"
