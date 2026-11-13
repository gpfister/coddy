"""Tests for Coddy schemas enforcing Rule R1 (The Structured Output Mandate)."""

import pytest
from pydantic import ValidationError

from app.coddy.agentic.schemas.plan import (
    Plan,
    PlanMetadata,
    PlanStructure,
    StepItem,
    TaskItem,
    TierItem,
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


def test_specification_valid():
    spec = Specification(
        version="1.0",
        metadata=SpecificationMetadata(project_name="test-project"),
        executive_brief="Brief summary.",
        business_requirements=BusinessRequirements(
            goals=["Goal 1"],
            target_kpis=["KPI 1"],
            rules=[RuleItem(rule_text="Rule 1", type="new")],
            use_cases=[UseCaseItem(id="uc_01", title="Title", content="Content")],
            test_cases=[TestCaseItem(id="tc_01", test_description="Desc", expected_outcome="Outcome")],
        ),
        functional_specification="Functional specs.",
        technical_requirements=TechnicalRequirements(
            architecture="Arch.",
            infrastructure="Infra.",
            repositories=[RepositoryItem(repo_name="repo1", action="create", instructions="Inst.")],
        ),
    )
    assert spec.version == "1.0"
    assert spec.metadata.project_name == "test-project"


def test_specification_extra_field_forbidden():
    with pytest.raises(ValidationError):
        Specification(
            version="1.0",
            metadata=SpecificationMetadata(project_name="test"),
            executive_brief="Brief.",
            extra_forbidden_key="arbitrary",  # Should fail Rule R1
            business_requirements=BusinessRequirements(
                goals=["G1"],
                target_kpis=["K1"],
                rules=[RuleItem(rule_text="R1", type="new")],
                use_cases=[UseCaseItem(id="uc_1", title="T", content="C")],
                test_cases=[TestCaseItem(id="tc_1", test_description="D", expected_outcome="O")],
            ),
            functional_specification="F",
            technical_requirements=TechnicalRequirements(
                architecture="A",
                infrastructure="I",
                repositories=[RepositoryItem(repo_name="r", action="create", instructions="i")],
            ),
        )


def test_plan_valid():
    plan = Plan(
        version="1.0",
        metadata=PlanMetadata(project_id="test-project", spec_reference_id="spec.json"),
        structure=PlanStructure(
            tiers=[
                TierItem(
                    tier_id="T1",
                    title="Tier 1",
                    steps=[
                        StepItem(
                            step_id="S1_1",
                            type="sequential",
                            tasks=[TaskItem(task_id="TASK_01", label="Init", status="pending", instructions="Do it")],
                        )
                    ],
                )
            ]
        ),
    )
    assert plan.structure.tiers[0].steps[0].tasks[0].task_id == "TASK_01"


def test_normalize_specification_recovers_from_validation_errors():
    """Verify that loose LLM outputs with root-level fields and extra keys are normalized into a valid Specification."""
    loose_output = {
        "project_name": "coddy-project",
        "goals": [{"id": "goal_01", "description": "Sanitize user request and pass to the orchestrator."}],
        "rules": [
            {
                "id": "rule_01",
                "description": "The sanitize agent must be executed before the orchestrator.",
                "type": "new",
            }
        ],
        "use_cases": [
            {"id": "uc_01", "name": "Run pipeline", "description": "Execute the pipeline based on the metadata."}
        ],
        "test_cases": [
            {"id": "tc_01", "name": "Verify pipeline execution", "expected": "sanitize_output == orchestrator_input"}
        ],
        "architecture": {
            "infrastructure": ["Agent pipeline orchestrator to route request to coding-orchestrate agent."]
        },
        "repositories": [{"name": "coddy-pipeline", "dependencies": ["httpx"]}],
    }

    # Direct validation must fail due to extra forbidden keys and missing required keys (Rule R1)
    with pytest.raises(ValidationError) as exc_info:
        Specification.model_validate(loose_output)
    assert len(exc_info.value.errors()) == 12

    # Normalization must succeed and yield a valid Specification instance
    from app.coddy.agentic.schemas.specification import normalize_specification_data

    normalized = normalize_specification_data(loose_output, default_project_name="coddy-project")
    spec = Specification.model_validate(normalized)

    assert spec.version == "1.0"
    assert spec.metadata.project_name == "coddy-project"
    assert "Sanitize user request" in spec.business_requirements.goals[0]
    assert (
        spec.business_requirements.rules[0].rule_text == "The sanitize agent must be executed before the orchestrator."
    )
    assert spec.business_requirements.rules[0].type == "new"
    assert spec.business_requirements.use_cases[0].title == "Run pipeline"
    assert spec.business_requirements.use_cases[0].content == "Execute the pipeline based on the metadata."
    assert spec.business_requirements.test_cases[0].test_description == "Verify pipeline execution"
    assert spec.business_requirements.test_cases[0].expected_outcome == "sanitize_output == orchestrator_input"
    assert spec.technical_requirements.repositories[0].repo_name == "coddy-pipeline"
    assert spec.technical_requirements.repositories[0].action == "change"
    assert "httpx" in spec.technical_requirements.repositories[0].instructions
    assert spec.executive_brief
    assert spec.functional_specification


def test_specification_feature_lifecycle_types():
    """Verify Specification supports feature_add, feature_modify, and feature_remove."""
    # Feature Add
    spec_add = Specification(
        version="1.0",
        metadata=SpecificationMetadata(
            project_name="my-app",
            spec_type="feature_add",
            feature_name="dark-mode",
        ),
        executive_brief="Add dark mode support.",
        business_requirements=BusinessRequirements(
            goals=["Enhance UX in low light"],
            target_kpis=["Adoption by 40% of users"],
            rules=[RuleItem(rule_text="Preserve user preference in local storage", type="new")],
            use_cases=[UseCaseItem(id="uc_01", title="Toggle Theme", content="User toggles theme.")],
            test_cases=[
                TestCaseItem(
                    id="tc_01",
                    test_description="Check theme persistence",
                    expected_outcome="Theme persists across reloads",
                )
            ],
        ),
        functional_specification="Theme switching logic and state management.",
        technical_requirements=TechnicalRequirements(
            architecture="CSS variable theming.",
            infrastructure="No infra changes.",
            repositories=[RepositoryItem(repo_name="ui-web", action="change", instructions="Add theme provider.")],
        ),
    )
    assert spec_add.metadata.spec_type == "feature_add"
    assert spec_add.metadata.feature_name == "dark-mode"

    # Feature Modify with impact_analysis
    spec_modify = Specification(
        version="1.0",
        metadata=SpecificationMetadata(
            project_name="my-app",
            spec_type="feature_modify",
            feature_name="auth-tokens",
        ),
        executive_brief="Migrate from opaque tokens to JWTs.",
        business_requirements=BusinessRequirements(
            goals=["Reduce database lookups"],
            target_kpis=["Auth latency < 10ms"],
            rules=[
                RuleItem(rule_text="Token format changed to RFC 7519 JWT", type="updated"),
                RuleItem(rule_text="HTTPS required for all requests", type="existing"),
            ],
            use_cases=[UseCaseItem(id="uc_01", title="Verify JWT", content="Service validates signature.")],
            test_cases=[
                TestCaseItem(id="tc_01", test_description="Validate JWT expiry", expected_outcome="401 Unauthorized")
            ],
        ),
        functional_specification="JWT signing, issuance, and verification workflows.",
        technical_requirements=TechnicalRequirements(
            architecture="Stateless JWT verification with asymmetric keys.",
            infrastructure="Key rotation secrets manager.",
            repositories=[
                RepositoryItem(repo_name="auth-svc", action="change", instructions="Implement JWT provider.")
            ],
            impact_analysis="Breaking Change: Legacy opaque tokens will be deprecated over a 30-day grace period.",
        ),
    )
    assert spec_modify.metadata.spec_type == "feature_modify"
    assert spec_modify.technical_requirements.impact_analysis is not None

    # Feature Remove
    spec_remove = Specification(
        version="1.0",
        metadata=SpecificationMetadata(
            project_name="my-app",
            spec_type="feature_remove",
            feature_name="legacy-v1-api",
        ),
        executive_brief="Decommission legacy v1 endpoints.",
        business_requirements=BusinessRequirements(
            goals=["Eliminate technical debt"],
            target_kpis=["Zero traffic to v1 endpoints"],
            rules=[
                RuleItem(rule_text="v1 routing disabled", type="bypassed"),
            ],
            use_cases=[UseCaseItem(id="uc_01", title="Reject v1 Requests", content="Return 410 Gone.")],
            test_cases=[TestCaseItem(id="tc_01", test_description="Call /v1/users", expected_outcome="410 Gone")],
        ),
        functional_specification="Removal of v1 controllers and routing.",
        technical_requirements=TechnicalRequirements(
            architecture="Direct all traffic to v2.",
            infrastructure="Remove v1 ingress route.",
            repositories=[
                RepositoryItem(repo_name="api-gateway", action="change", instructions="Remove v1 routing rules."),
                RepositoryItem(repo_name="v1-controller", action="remove", instructions="Delete controller module."),
            ],
            impact_analysis="All callers must migrate to /v2 before deployment.",
        ),
    )
    assert spec_remove.metadata.spec_type == "feature_remove"
    assert spec_remove.technical_requirements.repositories[1].action == "remove"


def test_normalize_specification_feature_modes():
    """Verify normalize_specification_data correctly normalizes feature types, feature_name, and impact_analysis."""
    from app.coddy.agentic.schemas.specification import normalize_specification_data

    raw = {
        "metadata": {
            "project_name": "ecommerce",
            "type": "modify_feature",
            "feature_name": "cart-checkout",
        },
        "summary": "Update checkout flow to support 1-click payments.",
        "goals": ["Faster checkout"],
        "target_kpis": ["Checkout completion rate +15%"],
        "rules": [{"rule": "1-click requires pre-saved payment method", "type": "new"}],
        "use_cases": [{"name": "1-Click Checkout", "details": "User clicks buy now."}],
        "test_cases": [{"scenario": "User with saved card", "assertion": "Order created immediately"}],
        "architecture": "Event-driven checkout processing.",
        "infrastructure": "Payment gateway webhook listeners.",
        "repositories": [{"name": "checkout-svc", "action": "change", "instructions": "Update flow."}],
        "impact_analysis": "Adds new column `preferred_payment_method_id` to user_profiles table.",
    }

    normalized = normalize_specification_data(raw)
    spec = Specification.model_validate(normalized)
    assert spec.metadata.spec_type == "feature_modify"
    assert spec.metadata.feature_name == "cart-checkout"
    assert (
        spec.technical_requirements.impact_analysis
        == "Adds new column `preferred_payment_method_id` to user_profiles table."
    )


def test_normalize_plan_recovers_from_loose_structure():
    """Verify that loose LLM outputs for Plan are normalized into a valid Plan."""
    from app.coddy.agentic.schemas.plan import normalize_plan_data

    loose_plan = {
        "project_id": "coddy-project",
        "tiers": [
            {
                "name": "Phase 1: Foundation",
                "steps": [
                    {
                        "type": "sequential",
                        "tasks": [{"name": "Setup Router", "description": "Configure routing in orchestrator."}],
                    }
                ],
            }
        ],
    }

    normalized = normalize_plan_data(loose_plan, default_project_id="coddy-project", default_spec_ref="spec.json")
    plan = Plan.model_validate(normalized)

    assert plan.version == "1.0"
    assert plan.metadata.project_id == "coddy-project"
    assert plan.structure.tiers[0].title == "Phase 1: Foundation"
    assert plan.structure.tiers[0].steps[0].tasks[0].label == "Setup Router"
    assert plan.structure.tiers[0].steps[0].tasks[0].instructions == "Configure routing in orchestrator."
    assert plan.structure.tiers[0].steps[0].tasks[0].status == "pending"


def test_sanitized_user_request_forbid_extra():
    """Verify Rule R1 (extra='forbid') on SanitizedUserRequest and AmbiguousTerm."""
    from app.coddy.agentic.schemas.sanitize import (
        AmbiguousTerm,
        SanitizedUserRequest,
    )

    with pytest.raises(ValidationError):
        SanitizedUserRequest(
            user_request="Refactor service",
            unexpected_field="disallowed",
        )

    with pytest.raises(ValidationError):
        AmbiguousTerm(
            term="term",
            meanings=["m1"],
            extra_field="bad",
        )


def test_intents_json_valid():
    """Verify that docs/intents.json exists and adheres to schema."""
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    intents_path = repo_root / "docs" / "intents.json"

    assert intents_path.is_file(), f"docs/intents.json must exist at {intents_path}"

    data = json.loads(intents_path.read_text(encoding="utf-8"))
    assert "intent_types" in data
    assert "intents" in data

    expected_types = {
        "cli_interface",
        "agent_workflow",
        "tool_usage",
        "database_operation",
        "file_io",
        "external_api",
        "callback_dispatch",
        "artifact_transformation",
    }
    assert set(data["intent_types"].keys()) == expected_types

    required_keys = {"id", "type", "subject", "predicate", "object", "source_file", "line_anchor", "description"}
    intents = data["intents"]
    assert len(intents) >= 40

    for item in intents:
        assert required_keys.issubset(item.keys()), f"Intent {item.get('id')} missing required fields"
        assert item["type"] in expected_types
        src_file = repo_root / item["source_file"]
        assert src_file.is_file(), f"Source file {item['source_file']} for intent {item['id']} not found on disk"


def test_unknowns_json_valid():
    """Verify that docs/unknowns.json exists and adheres to schema and file references."""
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    unknowns_path = repo_root / "docs" / "unknowns.json"

    assert unknowns_path.is_file(), f"docs/unknowns.json must exist at {unknowns_path}"

    data = json.loads(unknowns_path.read_text(encoding="utf-8"))
    assert "version" in data
    assert "unknowns" in data

    expected_categories = {
        "disconnected_callback",
        "unwired_cli_flag",
        "unused_config",
        "uninvoked_preflight",
        "unreferenced_helper",
        "unused_tool",
        "unwired_schema",
        "unimplemented_storage",
        "stub_step_node",
    }

    required_keys = {
        "id",
        "symbol",
        "source_file",
        "line_anchor",
        "category",
        "description",
        "impact",
        "recommendation",
    }

    unknowns = data["unknowns"]
    assert len(unknowns) >= 1

    for item in unknowns:
        assert required_keys.issubset(item.keys()), f"Unknown {item.get('id')} missing required fields"
        assert item["category"] in expected_categories, (
            f"Unknown {item.get('id')} has unexpected category {item.get('category')}"
        )
        src_file = repo_root / item["source_file"]
        assert src_file.is_file(), f"Source file {item['source_file']} for unknown {item['id']} not found on disk"


def test_research_plan_valid():
    """Verify strict validation and schema conformity for ResearchPlan."""
    from app.coddy.agentic.schemas.research_plan import (
        ResearchPlan,
        ResearchPlanApproach,
        ResearchPlanSubject,
        ResearchPlanTopic,
    )

    plan = ResearchPlan(
        rationale="Break down the real-time notification engine into core subjects",
        topics=[
            ResearchPlanTopic(
                topic="Architecture & Protocols",
                description="Transport and messaging protocols",
                subjects=[
                    ResearchPlanSubject(
                        title="Transport Layer",
                        description="Evaluate WebSockets vs SSE for bidirectional messaging",
                        target_sources=["code", "document"],
                        open_issues=["How does the server handle heartbeat timeouts under mobile reconnections?"],
                        approaches=[
                            ResearchPlanApproach(
                                name="WebSocket Server",
                                description="Bidirectional full-duplex socket channel",
                                rationale="Sub-100ms latency requirement",
                            )
                        ],
                    ),
                    ResearchPlanSubject(
                        title="State Synchronization",
                        description="Investigate Redis Pub/Sub for distributed node sync",
                        target_sources=["code", "web"],
                        open_issues=["What is the maximum message fanout before Redis CPU saturation?"],
                    ),
                ],
            )
        ],
    )
    assert plan.rationale.startswith("Break down")
    assert len(plan.topics) == 1
    assert plan.topics[0].topic == "Architecture & Protocols"
    assert len(plan.topics[0].subjects) == 2
    assert plan.topics[0].subjects[0].open_issues == [
        "How does the server handle heartbeat timeouts under mobile reconnections?"
    ]
    assert plan.topics[0].subjects[0].approaches[0].name == "WebSocket Server"


def test_research_plan_extra_field_forbidden():
    """Verify extra='forbid' on ResearchPlan and nested models."""
    from app.coddy.agentic.schemas.research_plan import (
        ResearchPlan,
        ResearchPlanApproach,
        ResearchPlanSubject,
        ResearchPlanTopic,
    )

    with pytest.raises(ValidationError):
        ResearchPlanApproach(
            name="Approach",
            description="Desc",
            rationale="Rationale",
            unknown_key="disallowed",
        )

    with pytest.raises(ValidationError):
        ResearchPlanSubject(
            title="Sub",
            description="Foc",
            extra_field="disallowed",
        )

    with pytest.raises(ValidationError):
        ResearchPlanTopic(
            topic="Top",
            subjects=[],
            extra_field="disallowed",
        )

    with pytest.raises(ValidationError):
        ResearchPlan(
            rationale="Test",
            topics=[],
            extra_field="disallowed",
        )


def test_research_plan_rejects_placeholders():
    """Verify that ResearchPlan rejects placeholder strings like '...' or 'TODO'."""
    from app.coddy.agentic.schemas.research_plan import (
        ResearchPlan,
        ResearchPlanApproach,
        ResearchPlanSubject,
        ResearchPlanTopic,
    )

    # Rationale placeholder
    with pytest.raises(ValidationError) as exc_info:
        ResearchPlan(
            rationale="...",
            topics=[
                ResearchPlanTopic(
                    topic="Architecture",
                    subjects=[ResearchPlanSubject(title="S1", description="D1")],
                )
            ],
        )
    assert "cannot be a placeholder" in str(exc_info.value)

    # Topic name placeholder
    with pytest.raises(ValidationError) as exc_info:
        ResearchPlan(
            rationale="Valid rationale for research plan.",
            topics=[
                ResearchPlanTopic(
                    topic="...",
                    subjects=[ResearchPlanSubject(title="S1", description="D1")],
                )
            ],
        )
    assert "cannot be a placeholder" in str(exc_info.value)

    # Subject title placeholder
    with pytest.raises(ValidationError) as exc_info:
        ResearchPlan(
            rationale="Valid rationale for research plan.",
            topics=[
                ResearchPlanTopic(
                    topic="Architecture",
                    subjects=[ResearchPlanSubject(title="...", description="D1")],
                )
            ],
        )
    assert "cannot be a placeholder" in str(exc_info.value)

    # Approach name placeholder
    with pytest.raises(ValidationError) as exc_info:
        ResearchPlan(
            rationale="Valid rationale for research plan.",
            topics=[
                ResearchPlanTopic(
                    topic="Architecture",
                    subjects=[
                        ResearchPlanSubject(
                            title="S1",
                            description="D1",
                            approaches=[ResearchPlanApproach(name="...", description="D", rationale="R")],
                        )
                    ],
                )
            ],
        )
    assert "cannot be a placeholder" in str(exc_info.value)

    # Open issue placeholder
    with pytest.raises(ValidationError) as exc_info:
        ResearchPlan(
            rationale="Valid rationale for research plan.",
            topics=[
                ResearchPlanTopic(
                    topic="Architecture",
                    subjects=[
                        ResearchPlanSubject(
                            title="S1",
                            description="D1",
                            open_issues=["TODO"],
                        )
                    ],
                )
            ],
        )
    assert "cannot be a placeholder" in str(exc_info.value)


def test_normalize_research_plan_data():
    """Verify normalize_research_plan_data cleans loose LLM dictionary structures including open_issues."""
    from app.coddy.agentic.schemas.research_plan import (
        ResearchPlan,
        normalize_research_plan_data,
    )

    loose_data = {
        "rationale": "High-level plan for indexing",
        "topics": [
            {
                "name": "Storage Engines",
                "subjects": [
                    {
                        "title": "Embedded Qdrant",
                        "description": "Evaluate sparse vector BM25/BM42 scoring",
                        "open_issues": ["Does Qdrant embedded mode support concurrent indexing?"],
                    },
                    {
                        "title": "FalkorDB Graph",
                        "description": "Cypher querying",
                        "issues": [{"issue": "What memory overhead does FalkorDB require?"}],
                    },
                ],
            }
        ],
    }
    normalized = normalize_research_plan_data(loose_data)
    plan = ResearchPlan.model_validate(normalized)
    assert plan.rationale == "High-level plan for indexing"
    assert plan.topics[0].topic == "Storage Engines"
    assert plan.topics[0].subjects[0].title == "Embedded Qdrant"
    assert plan.topics[0].subjects[0].description == "Evaluate sparse vector BM25/BM42 scoring"
    assert plan.topics[0].subjects[0].open_issues == ["Does Qdrant embedded mode support concurrent indexing?"]
    assert plan.topics[0].subjects[1].open_issues == ["What memory overhead does FalkorDB require?"]


def test_sanitized_user_request_schema_and_normalization():
    """Verify SanitizedUserRequest schema with optional local_project_instructions and normalization."""
    from app.coddy.agentic.schemas.sanitize import (
        AmbiguousTerm,
        SanitizedUserRequest,
        normalize_sanitized_user_request_data,
    )

    req = SanitizedUserRequest(
        user_request="Build an authentication microservice",
        ambiguous_terms=[AmbiguousTerm(term="auth", meanings=["OAuth2", "JWT", "Session"])],
        local_project_instructions="Adhere to strict Pydantic v2 schemas and RTD guidelines.",
    )
    assert req.user_request == "Build an authentication microservice"
    assert req.local_project_instructions == "Adhere to strict Pydantic v2 schemas and RTD guidelines."
    assert not hasattr(req, "prompt")

    # Verify normalization with 'user_request' key
    raw_dict = {
        "user_request": "Create API gateway",
        "ambiguous_terms": [],
        "local_project_instructions": "Use FastAPI",
        "local_project_description": "# Gateway Project\n\nHigh performance API gateway.",
    }
    norm = normalize_sanitized_user_request_data(raw_dict)
    req2 = SanitizedUserRequest.model_validate(norm)
    assert req2.user_request == "Create API gateway"
    assert req2.local_project_instructions == "Use FastAPI"
    assert req2.local_project_description == "# Gateway Project\n\nHigh performance API gateway."

    # Verify 'prompt' key is not mapped (backward compatibility removed)
    legacy_dict = {
        "prompt": "Create legacy API gateway",
        "ambiguous_terms": [],
    }
    norm_legacy = normalize_sanitized_user_request_data(legacy_dict)
    assert norm_legacy["user_request"] == ""


def test_sanitize_input_schema_with_readme():
    """Verify SanitizeInput schema supports local_project_description and preserves extra='forbid'."""
    import pytest
    from pydantic import ValidationError

    from app.coddy.agentic.schemas.sanitize import SanitizeInput

    input_data = SanitizeInput(
        raw_user_request="Refactor logging subsystem",
        local_project_instructions="# Architecture Guide",
        local_project_description="# Project Overview",
    )
    assert input_data.raw_user_request == "Refactor logging subsystem"
    assert input_data.local_project_instructions == "# Architecture Guide"
    assert input_data.local_project_description == "# Project Overview"

    # Enforce extra='forbid' (Rule R1)
    with pytest.raises(ValidationError):
        SanitizeInput(raw_user_request="test", invalid_key="unexpected")


def test_enhanced_user_request_schema():
    """Verify EnhancedUserRequest schema validation, fields, and extra='forbid'."""
    import pytest
    from pydantic import ValidationError

    from app.coddy.agentic.schemas.enhanced_user_request import (
        ClarificationRecord,
        EnhancedUserRequest,
        normalize_enhanced_user_request_data,
    )

    clarification = ClarificationRecord(
        ambiguity_term="db",
        question="Which database engine should be used?",
        answer="SQLite with WAL mode enabled",
        rationale="Lightweight and local embedded storage",
    )
    enhanced = EnhancedUserRequest(
        user_request="Build an offline data storage module using SQLite with WAL mode.",
        clarifications=[clarification],
        local_project_instructions="Follow strict schemas",
        local_project_description="# Coddy DB",
    )
    assert enhanced.user_request.startswith("Build an offline")
    assert len(enhanced.clarifications) == 1
    assert enhanced.clarifications[0].ambiguity_term == "db"
    assert enhanced.local_project_instructions == "Follow strict schemas"
    assert enhanced.local_project_description == "# Coddy DB"

    # Enforce extra='forbid'
    with pytest.raises(ValidationError):
        EnhancedUserRequest(
            user_request="Invalid",
            unknown_field="forbidden",
        )

    # Test normalization
    raw_dict = {
        "user_request": "Normalized request",
        "clarifications": [
            {
                "ambiguity_term": "cache",
                "question": "Which cache?",
                "answer": "In-memory LRU",
                "rationale": "High speed",
            }
        ],
        "local_project_instructions": "AGENTS.md content",
        "local_project_description": "README.md content",
    }
    norm = normalize_enhanced_user_request_data(raw_dict)
    valid_model = EnhancedUserRequest.model_validate(norm)
    assert valid_model.user_request == "Normalized request"
    assert len(valid_model.clarifications) == 1
    assert valid_model.clarifications[0].answer == "In-memory LRU"
    assert valid_model.local_project_instructions == "AGENTS.md content"
    assert valid_model.local_project_description == "README.md content"


def test_research_schemas_and_normalization():
    """Verify EpisodeResearchResult, ResearchClarificationResult, and ResearchReport schemas."""
    from app.coddy.agentic.schemas.research import (
        CodeImpactReference,
        EpisodeResearchResult,
        MermaidDiagram,
        ProcessLogicDescription,
        ResearchClarificationResult,
        ResearchReport,
        ResolvedIssue,
        TechnicalAlternative,
        normalize_episode_research_data,
        normalize_research_clarification_data,
        normalize_research_report_data,
    )

    # 1. EpisodeResearchResult valid & extra forbid
    res = EpisodeResearchResult(
        subject_title="Authentication Architecture",
        summary_paragraph="Investigation of current auth flow and OAuth2 token refresh.",
        summary_bullets=["Point 1", "Point 2", "Point 3", "Point 4", "Point 5"],
        impacted_code_references=[
            CodeImpactReference(
                file_path="app/auth/client.py",
                symbol_name="AuthClient",
                description="Token exchange logic",
                impact_type="modify",
            )
        ],
        logic_and_rules_description="Checks bearer token expiration before each API call.",
        diagrams=[
            MermaidDiagram(
                title="Auth Flow",
                diagram_type="sequenceDiagram",
                code="Client->>AuthService: Login",
                description="Call sequence for user authentication.",
            )
        ],
        alternatives_and_tradeoffs=[
            TechnicalAlternative(
                name="JWT Refresh Tokens",
                description="Store refresh token in HTTP-only cookie.",
                pros=["Stateless", "High throughput"],
                cons=["Revocation latency"],
                recommendation="Recommended",
            )
        ],
        discovered_apis=["POST /v1/auth/token"],
        open_issues=["Should tokens support PKCE?"],
    )
    assert res.subject_title == "Authentication Architecture"
    assert len(res.summary_bullets) == 5
    assert len(res.diagrams) == 1
    assert res.diagrams[0].diagram_type == "sequenceDiagram"

    # Enforce extra='forbid'
    with pytest.raises(ValidationError):
        EpisodeResearchResult(
            subject_title="Invalid",
            summary_paragraph="Summary",
            summary_bullets=[],
            extra_field="forbidden",
        )

    # Test normalization of episode research
    raw_ep = {
        "subject_title": "Database Optimization",
        "summary_paragraph": "Evaluated SQLite WAL mode performance.",
        "summary_bullets": ["WAL mode reduces contention."],
        "open_issues": ["Lock concurrency"],
    }
    norm_ep = normalize_episode_research_data(raw_ep)
    ep_obj = EpisodeResearchResult.model_validate(norm_ep)
    assert ep_obj.subject_title == "Database Optimization"
    assert ep_obj.open_issues == ["Lock concurrency"]

    # 2. ResearchClarificationResult valid & normalization
    clar = ResearchClarificationResult(
        resolved_issues=[
            ResolvedIssue(
                issue="Should tokens support PKCE?",
                resolution="Yes, support PKCE for public clients.",
                source="user_clarification",
            )
        ],
        new_research_topics=[],
    )
    assert len(clar.resolved_issues) == 1
    assert clar.resolved_issues[0].source == "user_clarification"

    raw_clar = {
        "resolved_issues": [
            {
                "issue": "Which DB?",
                "resolution": "SQLite",
                "source": "inferred_from_research",
            }
        ],
        "new_research_topics": [
            {
                "topic": "SQLite Performance",
                "description": "Benchmark tests",
                "subjects": [
                    {
                        "title": "WAL Benchmark",
                        "description": "Measure write transactions per second",
                    }
                ],
            }
        ],
    }
    norm_clar = normalize_research_clarification_data(raw_clar)
    clar_obj = ResearchClarificationResult.model_validate(norm_clar)
    assert len(clar_obj.resolved_issues) == 1
    assert len(clar_obj.new_research_topics) == 1

    # 3. ResearchReport valid & normalization
    report = ResearchReport(
        executive_summary="Deep dive into authentication and persistence subsystems.",
        research_scope=["Authentication", "Persistence"],
        source_code_impact=[
            CodeImpactReference(
                file_path="app/auth.py",
                symbol_name="authenticate",
                description="Core auth function",
                impact_type="modify",
            )
        ],
        current_logic_and_processes=[
            ProcessLogicDescription(
                subsystem="Authentication",
                description="Validates tokens against database.",
                key_rules=["Token expiry 3600s"],
            )
        ],
        diagrams=[
            MermaidDiagram(
                title="Login Process",
                diagram_type="flowchart TD",
                code="A[Start] --> B[Verify]",
                description="Login process flowchart",
            ),
            MermaidDiagram(
                title="Token Refresh",
                diagram_type="sequenceDiagram",
                code="Client->>Server: Refresh",
                description="Token refresh call sequence",
            ),
        ],
        technical_alternatives_and_recommendations=[
            TechnicalAlternative(
                name="Option A",
                description="OAuth2 with PKCE",
                pros=["Secure"],
                cons=["Complex"],
                recommendation="Adopted",
            )
        ],
        clarification_log=[
            ResolvedIssue(
                issue="Token TTL",
                resolution="Set to 1 hour",
                source="user_clarification",
            )
        ],
    )
    assert report.executive_summary.startswith("Deep dive")
    assert len(report.diagrams) == 2

    # Normalization of report
    raw_rep = {
        "executive_summary": "Summary of findings",
        "source_code_impact": [],
    }
    norm_rep = normalize_research_report_data(raw_rep)
    rep_obj = ResearchReport.model_validate(norm_rep)
    assert rep_obj.executive_summary == "Summary of findings"
