"""Strict Pydantic schema for Coddy Specification artifacts.

Enforces Rule R1: The Structured Output Mandate (extra='forbid').
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SpecType = Literal["project_kickoff", "feature_add", "feature_modify", "feature_remove"]


class StrictBaseModel(BaseModel):
    """Base model forbidding unexpected keys."""

    model_config = ConfigDict(extra="forbid")


class SpecificationMetadata(StrictBaseModel):
    """Metadata describing the project specification."""

    project_name: str = Field(..., description="Project or system identifier")
    spec_type: SpecType = Field(
        default="project_kickoff",
        description="Lifecycle scope: kickoff new project, add feature, modify feature, or remove feature",
    )
    feature_name: str | None = Field(
        default=None,
        description="Name of the targeted feature if spec_type is feature-specific",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO-8601 formatted timestamp",
    )


class RuleItem(StrictBaseModel):
    """A single business or architectural rule."""

    rule_text: str = Field(..., description="Description of the business rule")
    type: Literal["new", "updated", "existing", "bypassed"] = Field(..., description="Rule lifecycle classification")


class UseCaseItem(StrictBaseModel):
    """A recursively expanded use case."""

    id: str = Field(..., description="Unique use case identifier (e.g. uc_01)")
    title: str = Field(..., description="Short title of the use case")
    content: str = Field(..., description="Detailed recursive expansion of the use case")


class TestCaseItem(StrictBaseModel):
    """A test case validating requirement fulfillment."""

    __test__ = False
    id: str = Field(..., description="Unique test case identifier (e.g. tc_01)")
    test_description: str = Field(..., description="Description of scenario under test")
    expected_outcome: str = Field(..., description="Expected assertion or behavior")


class BusinessRequirements(StrictBaseModel):
    """High-level business goals, KPIs, rules, use cases, and test cases."""

    goals: list[str] = Field(..., min_length=1, description="List of primary goals")
    target_kpis: list[str] = Field(..., min_length=1, description="List of target KPIs")
    rules: list[RuleItem] = Field(..., description="Business and compliance rules")
    use_cases: list[UseCaseItem] = Field(..., min_length=1, description="Granular, expanded use cases")
    test_cases: list[TestCaseItem] = Field(..., min_length=1, description="Granular, expanded test cases")


class RepositoryItem(StrictBaseModel):
    """Target repository or codebase module affected."""

    repo_name: str = Field(..., description="Name or path of the repository")
    action: Literal["create", "change", "remove"] = Field(..., description="Action to take on the repository")
    instructions: str = Field(..., description="Detailed technical instructions for repository changes")


class TechnicalRequirements(StrictBaseModel):
    """Architectural, infrastructural, and repository specifications."""

    architecture: str = Field(..., description="Detailed description of solution and software architecture")
    infrastructure: str = Field(..., description="Detailed instructions for infrastructure to build/change/remove")
    repositories: list[RepositoryItem] = Field(..., min_length=1, description="Affected repositories and modules")
    impact_analysis: str | None = Field(
        default=None,
        description="Detailed impact, migration, breaking change, or deprecation/removal analysis",
    )


class Specification(StrictBaseModel):
    """Root Specification artifact.

    Must strictly match the Coddy SPECIFICATION JSON schema.
    """

    version: Literal["1.0"] = Field(default="1.0", description="Schema version")
    metadata: SpecificationMetadata = Field(..., description="Project metadata")
    executive_brief: str = Field(..., description="Single paragraph summary for executive teams")
    business_requirements: BusinessRequirements = Field(
        ..., description="Business requirements, KPIs, rules, use cases, and test cases"
    )
    functional_specification: str = Field(..., description="Full documentation of processes, workflow, and logic")
    technical_requirements: TechnicalRequirements = Field(
        ..., description="Architecture, infrastructure, and repository requirements"
    )


def normalize_specification_data(raw: dict, default_project_name: str = "project") -> dict:
    """Normalizes arbitrary or loosely-structured LLM JSON output into a strictly valid Specification schema dict.

    Handles common LLM deviations:
    - Root-level placement of goals, rules, use_cases, test_cases, architecture, repositories.
    - Missing executive_brief or functional_specification.
    - Dict goals instead of string lists.
    - Missing or alternative field names (e.g. name instead of title, description instead of content/rule_text).
    - Dict/list architecture instead of string.
    - Forbidden extra fields removed to satisfy Rule R1 (extra='forbid').
    """
    # 1. Version
    version = "1.0"

    # 2. Metadata
    meta_raw = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    project_name = (
        str(meta_raw.get("project_name") or raw.get("project_name") or default_project_name).strip() or "project"
    )
    timestamp = str(meta_raw.get("timestamp") or datetime.now(UTC).isoformat())

    raw_spec_type = (
        str(
            meta_raw.get("spec_type")
            or raw.get("spec_type")
            or meta_raw.get("type")
            or raw.get("type")
            or "project_kickoff"
        )
        .lower()
        .strip()
    )
    spec_type_mapping = {
        "project_kickoff": "project_kickoff",
        "project": "project_kickoff",
        "kickoff": "project_kickoff",
        "new_project": "project_kickoff",
        "feature_add": "feature_add",
        "feature_new": "feature_add",
        "add_feature": "feature_add",
        "new_feature": "feature_add",
        "feature_modify": "feature_modify",
        "modify_feature": "feature_modify",
        "change_feature": "feature_modify",
        "feature_change": "feature_modify",
        "update_feature": "feature_modify",
        "feature_update": "feature_modify",
        "feature_remove": "feature_remove",
        "remove_feature": "feature_remove",
        "delete_feature": "feature_remove",
        "feature_delete": "feature_remove",
        "deprecate_feature": "feature_remove",
        "feature_deprecate": "feature_remove",
    }
    spec_type = spec_type_mapping.get(raw_spec_type, "project_kickoff")

    raw_feature_name = meta_raw.get("feature_name") or raw.get("feature_name")
    feature_name = str(raw_feature_name).strip() if raw_feature_name and str(raw_feature_name).strip() else None

    metadata = {
        "project_name": project_name,
        "spec_type": spec_type,
        "timestamp": timestamp,
    }
    if feature_name:
        metadata["feature_name"] = feature_name

    # 3. Business Requirements
    biz_raw = raw.get("business_requirements") if isinstance(raw.get("business_requirements"), dict) else {}

    # Goals
    raw_goals = biz_raw.get("goals") or raw.get("goals") or []
    if not isinstance(raw_goals, list):
        raw_goals = [raw_goals] if raw_goals else []
    goals: list[str] = []
    for g in raw_goals:
        if isinstance(g, dict):
            text = g.get("description") or g.get("goal") or g.get("title") or g.get("text") or str(g)
            if text:
                goals.append(str(text).strip())
        elif g:
            goals.append(str(g).strip())
    if not goals:
        goals = [f"Deliver technical implementation for {project_name}"]

    # Target KPIs
    raw_kpis = biz_raw.get("target_kpis") or raw.get("target_kpis") or biz_raw.get("kpis") or raw.get("kpis") or []
    if not isinstance(raw_kpis, list):
        raw_kpis = [raw_kpis] if raw_kpis else []
    target_kpis: list[str] = []
    for k in raw_kpis:
        if isinstance(k, dict):
            text = k.get("description") or k.get("kpi") or k.get("title") or k.get("text") or str(k)
            if text:
                target_kpis.append(str(text).strip())
        elif k:
            target_kpis.append(str(k).strip())
    if not target_kpis:
        target_kpis = [
            "100% adherence to defined functional and technical requirements",
            "Zero regression in pipeline execution tests",
        ]

    # Rules
    raw_rules = biz_raw.get("rules") or raw.get("rules") or []
    if not isinstance(raw_rules, list):
        raw_rules = [raw_rules] if raw_rules else []
    rules = []
    for idx, r in enumerate(raw_rules):
        if isinstance(r, dict):
            r_text = r.get("rule_text") or r.get("description") or r.get("rule") or r.get("text") or f"Rule {idx + 1}"
            r_type = str(r.get("type", "new")).lower().strip()
            if r_type not in ("new", "updated", "existing", "bypassed"):
                r_type = "new"
            rules.append({"rule_text": str(r_text).strip(), "type": r_type})
        elif r:
            rules.append({"rule_text": str(r).strip(), "type": "new"})
    if not rules:
        rules = [{"rule_text": "All components must strictly adhere to validated schema contracts.", "type": "new"}]

    # Use Cases
    raw_ucs = biz_raw.get("use_cases") or raw.get("use_cases") or []
    if not isinstance(raw_ucs, list):
        raw_ucs = [raw_ucs] if raw_ucs else []
    use_cases = []
    for idx, uc in enumerate(raw_ucs):
        if isinstance(uc, dict):
            uc_id = uc.get("id") or f"uc_{idx + 1:02d}"
            title = uc.get("title") or uc.get("name") or f"Use Case {idx + 1}"
            content = (
                uc.get("content")
                or uc.get("description")
                or uc.get("flow")
                or uc.get("details")
                or f"Execution flow for {title}."
            )
            use_cases.append({"id": str(uc_id).strip(), "title": str(title).strip(), "content": str(content).strip()})
        elif uc:
            use_cases.append(
                {
                    "id": f"uc_{idx + 1:02d}",
                    "title": f"Use Case {idx + 1}",
                    "content": str(uc).strip(),
                }
            )
    if not use_cases:
        use_cases = [
            {
                "id": "uc_01",
                "title": "Primary Execution Flow",
                "content": f"Execute standard workflow processing for {project_name}.",
            }
        ]

    # Test Cases
    raw_tcs = biz_raw.get("test_cases") or raw.get("test_cases") or []
    if not isinstance(raw_tcs, list):
        raw_tcs = [raw_tcs] if raw_tcs else []
    test_cases = []
    for idx, tc in enumerate(raw_tcs):
        if isinstance(tc, dict):
            tc_id = tc.get("id") or f"tc_{idx + 1:02d}"
            desc = (
                tc.get("test_description")
                or tc.get("description")
                or tc.get("name")
                or tc.get("scenario")
                or f"Verify scenario {idx + 1}"
            )
            expected = (
                tc.get("expected_outcome")
                or tc.get("expected")
                or tc.get("expected_result")
                or tc.get("outcome")
                or tc.get("assertion")
                or "Test passes with expected assertions."
            )
            test_cases.append(
                {
                    "id": str(tc_id).strip(),
                    "test_description": str(desc).strip(),
                    "expected_outcome": str(expected).strip(),
                }
            )
        elif tc:
            test_cases.append(
                {
                    "id": f"tc_{idx + 1:02d}",
                    "test_description": f"Verify scenario {idx + 1}",
                    "expected_outcome": str(tc).strip(),
                }
            )
    if not test_cases:
        test_cases = [
            {
                "id": "tc_01",
                "test_description": "Validate end-to-end requirement fulfillment",
                "expected_outcome": "All tests pass successfully with expected state.",
            }
        ]

    business_requirements = {
        "goals": goals,
        "target_kpis": target_kpis,
        "rules": rules,
        "use_cases": use_cases,
        "test_cases": test_cases,
    }

    # 4. Executive Brief
    brief = raw.get("executive_brief") or raw.get("summary") or raw.get("brief") or raw.get("description")
    if not brief or not isinstance(brief, str) or not brief.strip():
        primary_goal = goals[0] if goals else "requirements fulfillment"
        brief = f"Technical specification and engineering roadmap for project '{project_name}'. Core objective: {primary_goal}."
    else:
        brief = str(brief).strip()

    # 5. Functional Specification
    func_spec = raw.get("functional_specification") or raw.get("functional_specs") or raw.get("functional_requirements")
    if not func_spec or not isinstance(func_spec, str) or not func_spec.strip():
        uc_summary = " ".join(f"[{uc['id']} - {uc['title']}]: {uc['content']}" for uc in use_cases)
        func_spec = f"Functional architecture for {project_name}. Detailed workflows and procedures: {uc_summary}"
    else:
        func_spec = str(func_spec).strip()

    # 6. Technical Requirements
    tech_raw = raw.get("technical_requirements") if isinstance(raw.get("technical_requirements"), dict) else {}

    # Architecture
    raw_arch = tech_raw.get("architecture") if "architecture" in tech_raw else raw.get("architecture")
    if isinstance(raw_arch, dict):
        parts = []
        for k, v in raw_arch.items():
            if isinstance(v, list):
                parts.append(f"{k}: {', '.join(str(x) for x in v)}")
            else:
                parts.append(f"{k}: {v}")
        arch_str = " | ".join(parts) if parts else "Modular component architecture."
    elif isinstance(raw_arch, list):
        arch_str = "\n".join(str(x) for x in raw_arch)
    elif raw_arch:
        arch_str = str(raw_arch).strip()
    else:
        arch_str = "Modular component architecture adhering strictly to interface contracts."

    # Infrastructure
    raw_infra = (
        tech_raw.get("infrastructure")
        if "infrastructure" in tech_raw
        else (
            raw.get("architecture", {}).get("infrastructure")
            if isinstance(raw.get("architecture"), dict)
            else raw.get("infrastructure")
        )
    )
    if isinstance(raw_infra, dict):
        infra_str = " | ".join(f"{k}: {v}" for k, v in raw_infra.items())
    elif isinstance(raw_infra, list):
        infra_str = "\n".join(str(x) for x in raw_infra)
    elif raw_infra:
        infra_str = str(raw_infra).strip()
    else:
        infra_str = "Local Python runtime environment with required dependency isolation."

    # Repositories
    raw_repos = tech_raw.get("repositories") or raw.get("repositories") or []
    if not isinstance(raw_repos, list):
        raw_repos = [raw_repos] if raw_repos else []
    repositories = []
    for idx, repo in enumerate(raw_repos):
        if isinstance(repo, dict):
            repo_name = repo.get("repo_name") or repo.get("name") or repo.get("path") or f"{project_name}-module"
            action = str(repo.get("action", "change")).lower().strip()
            if action not in ("create", "change", "remove"):
                action = "change"
            instructions = repo.get("instructions") or repo.get("description")
            if not instructions:
                if deps := repo.get("dependencies"):
                    deps_str = ", ".join(str(d) for d in deps)
                    instructions = (
                        f"Configure dependencies: {deps_str}. Implement required changes according to specification."
                    )
                else:
                    instructions = "Implement technical requirements and verify integration tests."
            repositories.append(
                {
                    "repo_name": str(repo_name).strip(),
                    "action": action,
                    "instructions": str(instructions).strip(),
                }
            )
        elif repo:
            repositories.append(
                {
                    "repo_name": str(repo).strip(),
                    "action": "change",
                    "instructions": "Implement required changes according to specification.",
                }
            )
    if not repositories:
        repositories = [
            {
                "repo_name": f"{project_name}-core",
                "action": "create",
                "instructions": "Initialize project codebase and foundational modules.",
            }
        ]

    # Impact Analysis (optional)
    raw_impact = (
        tech_raw.get("impact_analysis")
        or raw.get("impact_analysis")
        or tech_raw.get("impact")
        or raw.get("impact")
        or tech_raw.get("migration_strategy")
        or raw.get("migration_strategy")
        or tech_raw.get("deprecation_plan")
        or raw.get("deprecation_plan")
    )
    impact_str = str(raw_impact).strip() if raw_impact and str(raw_impact).strip() else None

    technical_requirements = {
        "architecture": arch_str,
        "infrastructure": infra_str,
        "repositories": repositories,
    }
    if impact_str:
        technical_requirements["impact_analysis"] = impact_str

    # Return clean, schema-adhering dictionary with forbidden keys stripped
    return {
        "version": version,
        "metadata": metadata,
        "executive_brief": brief,
        "business_requirements": business_requirements,
        "functional_specification": func_spec,
        "technical_requirements": technical_requirements,
    }
