"""Clarification tools for the coding-ambiguity-clarifier agent."""

from typing import Any

from app.coddy.utils.services import get_ui_service


def ask_question(question: str, options: list[str] | None = None) -> dict[str, Any]:
    """Prompts the user interactively in the terminal to clarify an identified ambiguity.

    Args:
        question: The specific clarification question to ask the user.
        options: Optional list of candidate choices, interpretations, or technical approaches.

    Returns:
        A dictionary containing the user's selected or typed answer:
        {"result": "SUCCESS", "answer": <user_answer>}
    """
    ui = get_ui_service()
    answer = ui.ask_user(question=question, options=options)
    return {
        "result": "SUCCESS",
        "answer": answer,
    }
