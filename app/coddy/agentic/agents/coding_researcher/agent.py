"""Agent: coding_researcher (Worker Agent for episodic research).

Lean runtime powered by google-adk LlmAgent.
Model: gemini-3.8-flash with ThinkingLevel.MEDIUM.
Equipped with web_search and GraphRAG tools.
Executes deep research for a single episode (one subject) and produces an EpisodeResearchResult.
"""

from pathlib import Path

from google.adk.agents import LlmAgent
from google.genai import types

from app.coddy.agentic.helpers.instructions_helper import load_instructions
from app.coddy.agentic.schemas.research import EpisodeResearchResult
from app.coddy.agentic.tools.graphrag_tools import (
    execute_cypher,
    get_call_hierarchy,
    get_code_entity,
    search_documents,
    search_facts,
    web_search,
)
from app.coddy.helpers.schema_helpers import gemini_schema_before_model_callback


class CodingResearcherAgent(LlmAgent):
    """Worker Agent: Performs episodic technical research on a single subject."""

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
            name="coding_researcher",
            description="Performs deep episodic code and web research on a specific subject, generating structured findings, diagrams, and open issues.",
            model="gemini-3.8-flash",
            instruction=load_instructions((Path(__file__).parent / "INSTRUCTIONS.md").resolve()),
            tools=[
                web_search,
                search_facts,
                search_documents,
                execute_cypher,
                get_code_entity,
                get_call_hierarchy,
            ],
            output_schema=EpisodeResearchResult,
            output_key="episode_research_result",
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
