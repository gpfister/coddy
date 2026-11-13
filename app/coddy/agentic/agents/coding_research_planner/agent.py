"""Agent: coding_research_plan (STEP 2: coding-research-plan).

Lean runtime powered by google-adk Agent.
Mix of Cloud Gemini / Local Gemma models with 256K context size and heavy reasoning.
Decomposes sanitized user requests into a structured ResearchPlan artifact.
"""

from pathlib import Path

from google.adk.agents import LlmAgent
from google.genai import types

from app.coddy.agentic.helpers.instructions_helper import load_instructions
from app.coddy.agentic.schemas.research_plan import ResearchPlan
from app.coddy.helpers.schema_helpers import gemini_schema_before_model_callback


class CodingResearchPlannerAgent(LlmAgent):
    """Worker Agent: Decomposes sanitized user requests into research plans."""

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
            name="coding_research_planner",
            description="Decomposes sanitized user requests into a structured research plan grouped by topic.",
            model="gemini-3.8-flash",
            instruction=load_instructions((Path(__file__).parent / "INSTRUCTIONS.md").resolve()),
            tools=[],
            output_schema=ResearchPlan,
            output_key="research_plan",
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
