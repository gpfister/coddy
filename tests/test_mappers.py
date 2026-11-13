"""Tests for Coddy Mappers enforcing Rule R2 (The Mapping Requirement)."""

from app.coddy.agentic.mappers.plan_mapper import PlanMapper
from app.coddy.agentic.mappers.sanitize_mapper import SanitizeMapper
from app.coddy.agentic.mappers.spec_mapper import SpecificationMapper
from app.coddy.agentic.schemas.plan import (
    Plan,
    PlanMetadata,
    PlanStructure,
    StepItem,
    TaskItem,
    TierItem,
)
from app.coddy.agentic.schemas.sanitize import (
    AmbiguousTerm,
    SanitizedUserRequest,
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


def test_specification_mapper():
    spec = Specification(
        version="1.0",
        metadata=SpecificationMetadata(project_name="my-service"),
        executive_brief="An executive overview of my-service.",
        business_requirements=BusinessRequirements(
            goals=["High throughput", "Low latency"],
            target_kpis=["99.99% availability"],
            rules=[RuleItem(rule_text="All requests authenticated", type="new")],
            use_cases=[UseCaseItem(id="uc_01", title="User Login", content="Detailed steps for login.")],
            test_cases=[TestCaseItem(id="tc_01", test_description="Test Login", expected_outcome="Token returned")],
        ),
        functional_specification="Handles authentication and sessions.",
        technical_requirements=TechnicalRequirements(
            architecture="Microservices pattern.",
            infrastructure="Kubernetes cluster.",
            repositories=[RepositoryItem(repo_name="auth-core", action="create", instructions="Setup repo.")],
        ),
    )

    md = SpecificationMapper.to_markdown(spec)
    assert "# Technical Specification: my-service" in md
    assert "**Scope Type**: `Project Kickoff`" in md
    assert "## Executive Brief" in md
    assert "High throughput" in md
    assert "99.99% availability" in md
    assert "`NEW`" in md
    assert "#### `uc_01`: User Login" in md
    assert "Detailed steps for login." in md
    assert "`[CREATE]`" in md


def test_specification_mapper_feature_and_impact():
    """Verify SpecificationMapper renders feature metadata and impact analysis."""
    spec = Specification(
        version="1.0",
        metadata=SpecificationMetadata(
            project_name="payment-api",
            spec_type="feature_modify",
            feature_name="stripe-checkout",
        ),
        executive_brief="Upgrade Stripe SDK and checkout elements.",
        business_requirements=BusinessRequirements(
            goals=["Support Payment Intents API"],
            target_kpis=["< 1% payment failure rate"],
            rules=[RuleItem(rule_text="Use Stripe Elements v3", type="updated")],
            use_cases=[UseCaseItem(id="uc_01", title="Card Checkout", content="Execute 3DS authentication.")],
            test_cases=[
                TestCaseItem(id="tc_01", test_description="3DS challenge", expected_outcome="Redirect and confirm")
            ],
        ),
        functional_specification="Full PaymentIntent lifecycle and webhook confirmation.",
        technical_requirements=TechnicalRequirements(
            architecture="Asynchronous webhook handling via Redis queue.",
            infrastructure="Stripe webhook endpoint with HMAC validation.",
            repositories=[
                RepositoryItem(repo_name="payments-core", action="change", instructions="Update Stripe client.")
            ],
            impact_analysis="Breaking Change: Deprecates Charge API tokens. Callers must supply client_secret.",
        ),
    )

    md = SpecificationMapper.to_markdown(spec)
    assert "# Technical Specification: payment-api - Feature: stripe-checkout" in md
    assert "**Scope Type**: `Feature Modify`" in md
    assert "**Feature**: `stripe-checkout`" in md
    assert "### Impact Analysis" in md
    assert "Breaking Change: Deprecates Charge API tokens." in md
    assert "`[CHANGE]`" in md


def test_plan_mapper():
    plan = Plan(
        version="1.0",
        metadata=PlanMetadata(project_id="my-service", spec_reference_id="spec.json"),
        structure=PlanStructure(
            tiers=[
                TierItem(
                    tier_id="T1",
                    title="Setup",
                    steps=[
                        StepItem(
                            step_id="S1_1",
                            type="sequential",
                            tasks=[
                                TaskItem(
                                    task_id="TASK_01",
                                    label="Initialize DB",
                                    status="pending",
                                    instructions="Run migration script.",
                                )
                            ],
                        )
                    ],
                )
            ]
        ),
    )

    md = PlanMapper.to_markdown(plan)
    assert "# Execution Plan: my-service" in md
    assert "### Tier `T1`: Setup" in md
    assert "#### Step `S1_1` (*Sequential Execution*)" in md
    assert "[ ] `TASK_01`: Initialize DB (`PENDING`)" in md
    assert "Run migration script." in md


def test_sanitize_mapper():
    user_request_data = SanitizedUserRequest(
        user_request="Build a low-latency trading engine.",
        ambiguous_terms=[
            AmbiguousTerm(
                term="low-latency",
                meanings=["Sub-millisecond execution", "Tick-to-trade under 10 microseconds"],
            ),
            AmbiguousTerm(
                term="engine",
                meanings=["Matching engine", "Order routing gateway"],
            ),
        ],
    )
    md = SanitizeMapper.format_user_request(user_request_data)
    assert "## User request" in md
    assert "Build a low-latency trading engine." in md
    assert "## Ambiguous terms" in md
    assert '1. "low-latency" could mean:' in md
    assert "  - Sub-millisecond execution." in md
    assert "  - Tick-to-trade under 10 microseconds." in md
    assert '2. "engine" could mean:' in md
    assert "  - Matching engine." in md
    assert "  - Order routing gateway." in md

    # Empty ambiguous terms omits the section
    empty_data = SanitizedUserRequest(user_request="Simple task.")
    empty_md = SanitizeMapper.format_user_request(empty_data)
    assert "## User request" in empty_md
    assert "Simple task." in empty_md
    assert "## Ambiguous terms" not in empty_md


def test_research_plan_mapper():
    """Verify ResearchPlanMapper.to_markdown generates formatted Markdown artifact."""
    from app.coddy.agentic.mappers.research_plan_mapper import ResearchPlanMapper
    from app.coddy.agentic.schemas.research_plan import (
        ResearchPlan,
        ResearchPlanApproach,
        ResearchPlanSubject,
        ResearchPlanTopic,
    )

    plan = ResearchPlan(
        rationale="Systematic decomposition of the caching layer.",
        topics=[
            ResearchPlanTopic(
                topic="Cache Storage Engines",
                description="Evaluating distributed cache backends",
                subjects=[
                    ResearchPlanSubject(
                        title="Redis Cluster",
                        description="Examine Redis Sentinel vs Cluster mode for high availability",
                        target_sources=["code", "document"],
                        open_issues=["How does Redis Cluster handle partition recovery during network split-brain?"],
                        approaches=[
                            ResearchPlanApproach(
                                name="Client-side Caching",
                                description="RESP3 client caching with invalidation broadcast",
                                rationale="Eliminates network hops for hot keys",
                            )
                        ],
                    )
                ],
            )
        ],
    )
    md = ResearchPlanMapper.to_markdown(plan)
    assert "# RESEARCH PLAN" in md
    assert "Systematic decomposition of the caching layer." in md
    assert "### Topic 1: Cache Storage Engines" in md
    assert "Evaluating distributed cache backends" in md
    assert "##### 1.1 Redis Cluster" in md
    assert "Examine Redis Sentinel vs Cluster mode" in md
    assert "**Target Sources**: `code`, `document`" in md
    assert "**Open Issues to Resolve:**" in md
    assert "- How does Redis Cluster handle partition recovery during network split-brain?" in md
    assert "**Candidate Technical Approaches:**" in md
    assert "- **Client-side Caching**: RESP3 client caching with invalidation broadcast" in md
    assert "*Evaluation Criteria / Rationale*: Eliminates network hops for hot keys" in md


def test_research_plan_mapper_with_research_materials():
    """Verify ResearchPlanMapper renders research materials assessment correctly."""
    from app.coddy.agentic.mappers.research_plan_mapper import ResearchPlanMapper
    from app.coddy.agentic.schemas.research_plan import (
        ResearchMaterialAssessment,
        ResearchPlan,
        ResearchPlanTopic,
    )

    plan = ResearchPlan(
        rationale="Decomposing caching architecture.",
        topics=[ResearchPlanTopic(topic="Caching", description="Cache layer", subjects=[])],
        research_materials=[
            ResearchMaterialAssessment(
                file_path="docs/architecture.pdf",
                served_information="Defines Redis Sentinel topology and failover policies.",
                investigation_targets="Check sentinel connection pool in redis_client.py.",
                requires_internet_research=True,
                internet_research_rationale="Research Redis 7.2 sentinel client protocol changes.",
            ),
            ResearchMaterialAssessment(
                file_path="specs/requirements.docx",
                served_information="States 99.99% availability requirement.",
                investigation_targets="Review failover timeouts in settings.",
                requires_internet_research=False,
            ),
        ],
    )
    md = ResearchPlanMapper.to_markdown(plan)
    assert "# RESEARCH PLAN" in md
    assert "## Research Materials Assessment" in md
    assert "### Material 1: `docs/architecture.pdf`" in md
    assert "**Served Information**:\nDefines Redis Sentinel topology and failover policies." in md
    assert "**Code/Documentation Investigation Targets**:\nCheck sentinel connection pool in redis_client.py." in md
    assert "**Requires External Web Research**: Yes" in md
    assert "*Web Research Rationale*: Research Redis 7.2 sentinel client protocol changes." in md
    assert "### Material 2: `specs/requirements.docx`" in md
    assert "**Requires External Web Research**: No" in md


def test_sanitize_mapper_with_local_project_instructions():
    """Verify SanitizeMapper formats SanitizedUserRequest with local instructions."""
    data = SanitizedUserRequest(
        user_request="Build high-performance search engine.",
        ambiguous_terms=[AmbiguousTerm(term="high-performance", meanings=["Sub-second queries", "10K QPS"])],
        local_project_instructions="Follow FalkorDB graph indexing invariants.",
    )
    user_md = SanitizeMapper.format_user_request(data)
    assert "## User request" in user_md
    assert "Build high-performance search engine." in user_md
    assert "## Ambiguous terms" in user_md
    assert '1. "high-performance" could mean:' in user_md

    instructions_md = SanitizeMapper.format_local_project_instructions(data)
    assert "## Sanitized local project instructions" in instructions_md
    assert "Follow FalkorDB graph indexing invariants." in instructions_md


def test_sanitize_mapper_with_local_project_description():
    """Verify SanitizeMapper formats SanitizedUserRequest with local_project_description and modular formatters."""
    data = SanitizedUserRequest(
        user_request="Build high-performance search engine.",
        ambiguous_terms=[AmbiguousTerm(term="high-performance", meanings=["Sub-second queries", "10K QPS"])],
        local_project_instructions="Follow FalkorDB graph indexing invariants.",
        local_project_description="# Coddy Search\n\nLean overview of search project.",
    )
    user_md = SanitizeMapper.format_user_request(data)
    assert "## User request" in user_md
    assert "## Ambiguous terms" in user_md
    assert "## Sanitized local project instructions" not in user_md

    instructions_md = SanitizeMapper.format_local_project_instructions(data)
    assert "Follow FalkorDB graph indexing invariants." in instructions_md

    readme_md = SanitizeMapper.format_local_project_description(data)
    assert "## Sanitized local project description" in readme_md
    assert "# Coddy Search" in readme_md


def test_enhanced_user_request_mapper():
    """Verify EnhancedUserRequestMapper renders ENHANCED_USER_REQUEST.md correctly."""
    from app.coddy.agentic.mappers.enhanced_user_request_mapper import EnhancedUserRequestMapper
    from app.coddy.agentic.schemas.enhanced_user_request import (
        ClarificationRecord,
        EnhancedUserRequest,
    )

    enhanced = EnhancedUserRequest(
        user_request="Build high-performance search engine with Sub-second queries.",
        clarifications=[
            ClarificationRecord(
                ambiguity_term="high-performance",
                question="What latency target do you expect?",
                answer="Sub-second queries (<500ms)",
                rationale="Selected sub-second latency target",
            )
        ],
        local_project_instructions="Strict typing",
        local_project_description="# Search",
    )

    md = EnhancedUserRequestMapper.to_markdown(enhanced)
    assert "## Enhanced User Request" in md
    assert "Build high-performance search engine with Sub-second queries." in md
    assert "## Clarifications & Resolved Ambiguities" in md
    assert "`high-performance`" in md
    assert "What latency target do you expect?" in md
    assert "Sub-second queries (<500ms)" in md
    assert "Selected sub-second latency target" in md

    inst_md = EnhancedUserRequestMapper.format_local_project_instructions(enhanced)
    assert "Strict typing" in inst_md

    readme_md = EnhancedUserRequestMapper.format_local_project_description(enhanced)
    assert "# Search" in readme_md


def test_episode_research_mapper():
    """Verify EpisodeResearchMapper converts EpisodeResearchResult to clean Markdown."""
    from app.coddy.agentic.mappers.research_mapper import EpisodeResearchMapper
    from app.coddy.agentic.schemas.research import (
        CodeImpactReference,
        EpisodeResearchResult,
        MermaidDiagram,
        TechnicalAlternative,
    )

    result = EpisodeResearchResult(
        subject_title="Authentication Architecture",
        summary_paragraph="Evaluated authentication flows and tokens.",
        summary_bullets=["Bullet 1", "Bullet 2", "Bullet 3", "Bullet 4", "Bullet 5"],
        impacted_code_references=[
            CodeImpactReference(
                file_path="app/auth/client.py",
                symbol_name="AuthClient",
                description="Token exchange client class",
                impact_type="modify",
            )
        ],
        logic_and_rules_description="Requires HMAC verification on every request.",
        diagrams=[
            MermaidDiagram(
                title="Auth Call Sequence",
                diagram_type="sequenceDiagram",
                code="Client->>Auth: Request",
                description="Authentication sequence",
            )
        ],
        alternatives_and_tradeoffs=[
            TechnicalAlternative(
                name="OAuth2 PKCE",
                description="Public client auth",
                pros=["Standardized", "Secure"],
                cons=["Complex"],
                recommendation="Use PKCE",
            )
        ],
        discovered_apis=["GET /v1/userinfo"],
        open_issues=["Token revocation endpoint latency"],
    )

    md = EpisodeResearchMapper.to_markdown(result)
    assert "# RESEARCH EPISODE: AUTHENTICATION ARCHITECTURE" in md
    assert "Evaluated authentication flows and tokens." in md
    assert "- Bullet 1" in md
    assert "`app/auth/client.py`" in md
    assert "Requires HMAC verification on every request." in md
    assert "```sequenceDiagram\nClient->>Auth: Request\n```" in md
    assert "### Option: OAuth2 PKCE" in md
    assert "**Recommendation**: Use PKCE" in md
    assert "- [ ] Token revocation endpoint latency" in md


def test_research_report_mapper():
    """Verify ResearchReportMapper converts ResearchReport to the 6-section RESEARCH_REPORT.md."""
    from app.coddy.agentic.mappers.research_mapper import ResearchReportMapper
    from app.coddy.agentic.schemas.research import (
        CodeImpactReference,
        MermaidDiagram,
        ProcessLogicDescription,
        ResearchReport,
        ResolvedIssue,
        TechnicalAlternative,
    )

    report = ResearchReport(
        executive_summary="Executive synthesis of all findings across auth and storage subsystems.",
        research_scope=["Authentication", "Storage"],
        source_code_impact=[
            CodeImpactReference(
                file_path="app/engine/core.py",
                symbol_name="run_engine",
                description="Main engine loop",
                impact_type="modify",
            )
        ],
        current_logic_and_processes=[
            ProcessLogicDescription(
                subsystem="Execution Engine",
                description="Step-by-step pipeline execution.",
                key_rules=["Rule A: Hermetic execution"],
            )
        ],
        diagrams=[
            MermaidDiagram(
                title="Engine Flow",
                diagram_type="flowchart TD",
                code="A --> B",
                description="Engine execution flow",
            ),
            MermaidDiagram(
                title="Call Flow",
                diagram_type="sequenceDiagram",
                code="A ->> B: ping",
                description="Ping call flow",
            ),
        ],
        technical_alternatives_and_recommendations=[
            TechnicalAlternative(
                name="Approach 1",
                description="Asyncio Event Loop",
                pros=["High concurrency"],
                cons=["Cooperative multitasking"],
                recommendation="Adopted",
            )
        ],
        clarification_log=[
            ResolvedIssue(
                issue="Async runtime timeout?",
                resolution="Set default to 300 seconds",
                source="user_clarification",
            )
        ],
    )

    md = ResearchReportMapper.to_markdown(report)
    assert "# TECHNICAL RESEARCH REPORT" in md
    assert "## 1. Executive Summary & Research Scope" in md
    assert "Executive synthesis of all findings" in md
    assert "## 3. Source Code Impact Analysis" in md
    assert "| `app/engine/core.py` | `run_engine` | `modify` | Main engine loop |" in md
    assert "## 4. Current Logic & Process Implementations" in md
    assert "### Subsystem: Execution Engine" in md
    assert "Rule A: Hermetic execution" in md
    assert "```flowchart TD\nA --> B\n```" in md
    assert "```sequenceDiagram\nA ->> B: ping\n```" in md
    assert "## 5. Technical Alternatives, Trade-offs & Recommendations" in md
    assert "### Alternative: Approach 1" in md
    assert "**Technical Recommendation**: Adopted" in md
    assert "## 6. Clarification Log & Resolved Decisions" in md
    assert "Async runtime timeout?" in md
    assert "Set default to 300 seconds" in md
