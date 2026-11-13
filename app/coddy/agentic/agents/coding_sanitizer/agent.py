"""Agent: coding_sanitize (STEP 1: coding-sanitize).

Lean runtime powered by google-adk Agent.
Mix of Cloud Gemini / Local Gemma models with 256K context size.
Sanitizes raw user requirements into a structured SanitizedUserRequest schema and maps to Markdown.
"""

from pathlib import Path

from google.adk.agents import LlmAgent
from google.genai import types

from app.coddy.agentic.helpers.instructions_helper import load_instructions
from app.coddy.agentic.schemas.sanitize import SanitizedUserRequest
from app.coddy.helpers.schema_helpers import gemini_schema_before_model_callback


class CodingSanitizerAgent(LlmAgent):
    """Worker Agent: Sanitizes raw user requirements."""

    def __init__(
        self,
        /,
        before_agent_callback=None,
        after_agent_callback=None,
        before_model_callback=None,
        after_model_callback=None,
    ):
        model_callbacks = [gemini_schema_before_model_callback]
        if before_model_callback:
            if isinstance(before_model_callback, list):
                model_callbacks.extend(before_model_callback)
            else:
                model_callbacks.append(before_model_callback)

        super().__init__(
            name="coding_sanitizer",
            description="Sanitizes raw input, local project instructions (AGENTS.md), and local project description (README.md) into a structured SanitizedUserRequest.",
            model="gemini-3.5-flash-lite",
            instruction=load_instructions((Path(__file__).parent / "INSTRUCTIONS.md").resolve()),
            tools=[],
            output_schema=SanitizedUserRequest,
            output_key="sanitized_user_request",
            generate_content_config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.LOW,
                    include_thoughts=True,
                ),
                temperature=0.2,
            ),
            before_agent_callback=before_agent_callback,
            after_agent_callback=after_agent_callback,
            before_model_callback=model_callbacks,
            after_model_callback=after_model_callback,
        )
