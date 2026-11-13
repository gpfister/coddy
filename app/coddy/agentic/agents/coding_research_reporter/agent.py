"""Agent: coding_research_reporter (Synthesis of technical research report).

Lean runtime powered by google-adk LlmAgent.
Model: gemini-3.8-flash with ThinkingLevel.HIGH.
Synthesizes all episodic research results, research materials, and clarified issues into a
comprehensive 6-section ResearchReport designed directly for downstream specification.
"""

from pathlib import Path

from google.adk.agents import LlmAgent
from google.genai import types

from app.coddy.agentic.helpers.instructions_helper import load_instructions
from app.coddy.agentic.schemas.research import ResearchReport
from app.coddy.helpers.schema_helpers import gemini_schema_before_model_callback


class CodingResearchReporterAgent(LlmAgent):
    """Worker Agent: Synthesizes final technical research report."""

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
            name="coding_research_reporter",
            description="Assembles a comprehensive, high-fidelity research report from all research episodes, materials, and clarification decisions.",
            model="gemini-3.8-flash",
            instruction=load_instructions((Path(__file__).parent / "INSTRUCTIONS.md").resolve()),
            tools=[],
            output_schema=ResearchReport,
            output_key="research_report",
            generate_content_config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.HIGH,
                    include_thoughts=True,
                ),
                temperature=0.2,
            ),
            before_agent_callback=before_agent_callback,
            after_agent_callback=after_agent_callback,
            before_model_callback=model_callbacks,
            after_model_callback=after_model_callback,
        )
