"""Agent: coding_research_clarifier (Clarification of research open issues).

Lean runtime powered by google-adk LlmAgent.
Model: gemini-3.5-flash-lite with ThinkingLevel.LOW.
Equipped with ask_question tool.
Analyzes open issues raised during episodic research, resolves what it can from findings,
submits unresolved issues to the user, and enqueues new research topics if requested.
"""

from pathlib import Path

from google.adk.agents import LlmAgent
from google.genai import types

from app.coddy.agentic.helpers.instructions_helper import load_instructions
from app.coddy.agentic.schemas.research import ResearchClarificationResult
from app.coddy.agentic.tools.clarification_tools import ask_question
from app.coddy.helpers.schema_helpers import gemini_schema_before_model_callback


class CodingResearchClarifierAgent(LlmAgent):
    """Worker Agent: Resolves open research issues and clarifies unknowns with the user."""

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
            name="coding_research_clarifier",
            description="Analyzes open issues raised across research episodes, resolves known ones, and interacts with the user via ask_question.",
            model="gemini-3.5-flash-lite",
            instruction=load_instructions((Path(__file__).parent / "INSTRUCTIONS.md").resolve()),
            tools=[ask_question],
            output_schema=ResearchClarificationResult,
            output_key="research_clarification_result",
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
