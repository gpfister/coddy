"""Agent: coding_ambiguity_clarifier (STEP 2: coding-ambiguity-clarifier).

Lean runtime powered by google-adk Agent.
Mix of Cloud Gemini / Local Gemma models with 256K context size and ask_question tool.
Clarifies identified ambiguities with the user and produces an EnhancedUserRequest.
"""

from pathlib import Path

from google.adk.agents import LlmAgent
from google.genai import types

from app.coddy.agentic.helpers.instructions_helper import load_instructions
from app.coddy.agentic.schemas.enhanced_user_request import EnhancedUserRequest
from app.coddy.agentic.tools.clarification_tools import ask_question
from app.coddy.helpers.schema_helpers import gemini_schema_before_model_callback


class CodingAmbiguityClarifierAgent(LlmAgent):
    """Worker Agent: Clarifies identified ambiguities and produces enhanced user requests."""

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
            name="coding_ambiguity_clarifier",
            description="Clarifies identified ambiguities with the user through interactive questions and enhances the sanitized user request.",
            model="gemini-3.5-flash-lite",
            instruction=load_instructions((Path(__file__).parent / "INSTRUCTIONS.md").resolve()),
            tools=[ask_question],
            output_schema=EnhancedUserRequest,
            output_key="enhanced_user_request",
            generate_content_config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.MEDIUM,
                    include_thoughts=True,
                ),
                temperature=0.2,
            ),
            before_agent_callback=before_agent_callback,
            after_agent_callback=after_agent_callback,
            before_model_callback=model_callbacks,
            after_model_callback=after_model_callback,
        )
