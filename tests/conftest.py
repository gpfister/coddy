"""Pytest configuration and helpers for Coddy tests."""

from datetime import UTC, datetime

import pytest

from app.coddy.agentic.schemas.plan import (
    Plan,
    PlanMetadata,
    PlanStructure,
    StepItem,
    TaskItem,
    TierItem,
)
from app.coddy.agentic.schemas.research_plan import (
    ResearchPlan,
    ResearchPlanApproach,
    ResearchPlanSubject,
    ResearchPlanTopic,
)
from app.coddy.agentic.schemas.specification import (
    BusinessRequirements,
    RepositoryItem,
    RuleItem,
    Specification,
    SpecificationMetadata,
    TechnicalRequirements,
    TestCaseItem,
    UseCaseItem,
)
from app.coddy.helpers.env_helpers import load_environment

load_environment()


def create_sample_specification(project_name: str = "test_project") -> Specification:
    """Creates a strictly valid sample Specification adhering to schemas."""
    return Specification(
        version="1.0",
        metadata=SpecificationMetadata(
            project_name=project_name,
            timestamp=datetime.now(UTC).isoformat(),
        ),
        executive_brief=f"Executive brief for {project_name}.",
        business_requirements=BusinessRequirements(
            goals=["High performance", "Fault tolerance"],
            target_kpis=["99.99% availability", "< 50ms latency"],
            rules=[RuleItem(rule_text="All operations must be idempotent", type="new")],
            use_cases=[UseCaseItem(id="uc_01", title="Primary Action", content="Detailed steps for primary action.")],
            test_cases=[
                TestCaseItem(id="tc_01", test_description="Verify happy path", expected_outcome="Success 200 OK")
            ],
        ),
        functional_specification="Detailed workflow and functional logic.",
        technical_requirements=TechnicalRequirements(
            architecture="Microservices architecture with event stream.",
            infrastructure="Cloud deployment target.",
            repositories=[
                RepositoryItem(repo_name=f"{project_name}-core", action="create", instructions="Initialize repo.")
            ],
        ),
    )


def create_sample_plan(project_name: str = "test_project", spec_id: str = "spec_01") -> Plan:
    """Creates a strictly valid sample Plan adhering to schemas."""
    return Plan(
        version="1.0",
        metadata=PlanMetadata(
            project_id=project_name,
            spec_reference_id=spec_id,
            timestamp=datetime.now(UTC).isoformat(),
        ),
        structure=PlanStructure(
            tiers=[
                TierItem(
                    tier_id="T1",
                    title="Foundation",
                    steps=[
                        StepItem(
                            step_id="S1_1",
                            type="sequential",
                            tasks=[
                                TaskItem(
                                    task_id="TASK_01",
                                    label="Initialize Repository",
                                    status="pending",
                                    instructions="Set up directory and dependencies.",
                                )
                            ],
                        )
                    ],
                )
            ]
        ),
    )


def create_sample_research_plan() -> ResearchPlan:
    """Creates a strictly valid sample ResearchPlan adhering to schemas."""
    return ResearchPlan(
        rationale="Test research rationale",
        topics=[
            ResearchPlanTopic(
                topic="Architecture",
                description="Core architectural components",
                subjects=[
                    ResearchPlanSubject(
                        title="Recursive Task Decomposition",
                        description="Investigate worker agent execution and context bounds",
                        target_sources=["code", "document"],
                        approaches=[
                            ResearchPlanApproach(
                                name="Graph Workflow",
                                description="Modular services dispatch",
                                rationale="Clean separation of concerns",
                            )
                        ],
                    )
                ],
            )
        ],
    )


@pytest.fixture(autouse=True)
def mock_external_endpoints(monkeypatch):
    """Automatically mocks external HTTP calls during test suite."""
    import httpx

    class DefaultModelsResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": [
                    {"id": "google/gemma-4-12b"},
                    {"id": "google/gemma-4-e4b"},
                    {"id": "google/gemma-4-31b"},
                    {"id": "google/gemma-4-26b-a4b"},
                    {"id": "google/gemma-4-26b-a4b-qat"},
                ]
            }

    monkeypatch.setattr(httpx.Client, "get", lambda self, url: DefaultModelsResponse())
