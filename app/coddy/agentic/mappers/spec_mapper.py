"""Specification Mapper: JSON -> Markdown.

Enforces Rule R2: The Mapping Requirement.
Translates strictly validated JSON Specification into clear, professional Markdown.
"""

from app.coddy.agentic.schemas.specification import Specification


class SpecificationMapper:
    """Transforms a Specification schema instance into a human-readable Markdown document."""

    @classmethod
    def to_markdown(cls, spec: Specification | dict) -> str:
        if isinstance(spec, dict):
            spec_obj = Specification.model_validate(spec)
        else:
            spec_obj = spec

        lines: list[str] = []

        # Header & Metadata
        header_title = f"# Technical Specification: {spec_obj.metadata.project_name}"
        if spec_obj.metadata.feature_name:
            header_title += f" - Feature: {spec_obj.metadata.feature_name}"
        lines.append(header_title)
        lines.append("")
        lines.append(f"**Version**: `{spec_obj.version}`  ")
        scope_label = spec_obj.metadata.spec_type.replace("_", " ").title()
        lines.append(f"**Scope Type**: `{scope_label}`  ")
        if spec_obj.metadata.feature_name:
            lines.append(f"**Feature**: `{spec_obj.metadata.feature_name}`  ")
        lines.append(f"**Generated**: `{spec_obj.metadata.timestamp}`  ")
        lines.append("**Standard**: Coddy RTD (Recursive Task Decomposition)")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Executive Brief
        lines.append("## Executive Brief")
        lines.append("")
        lines.append(spec_obj.executive_brief.strip())
        lines.append("")

        # Business Requirements
        lines.append("## Business Requirements")
        lines.append("")
        lines.append("### Goals")
        for goal in spec_obj.business_requirements.goals:
            lines.append(f"- {goal.strip()}")
        lines.append("")

        lines.append("### Target KPIs")
        for kpi in spec_obj.business_requirements.target_kpis:
            lines.append(f"- {kpi.strip()}")
        lines.append("")

        lines.append("### Rules & Policies")
        lines.append("| Type | Rule Description |")
        lines.append("| :--- | :--- |")
        for rule in spec_obj.business_requirements.rules:
            badge = f"`{rule.type.upper()}`"
            lines.append(f"| {badge} | {rule.rule_text.strip()} |")
        lines.append("")

        lines.append("### Use Cases (Expanded)")
        for uc in spec_obj.business_requirements.use_cases:
            lines.append(f"#### `{uc.id}`: {uc.title}")
            lines.append("")
            lines.append(uc.content.strip())
            lines.append("")

        lines.append("### Test Cases (Validation Matrix)")
        lines.append("| ID | Test Scenario | Expected Outcome |")
        lines.append("| :--- | :--- | :--- |")
        for tc in spec_obj.business_requirements.test_cases:
            desc = tc.test_description.replace("\n", " ").strip()
            outcome = tc.expected_outcome.replace("\n", " ").strip()
            lines.append(f"| `{tc.id}` | {desc} | {outcome} |")
        lines.append("")

        # Functional Specification
        lines.append("## Functional Specification")
        lines.append("")
        lines.append(spec_obj.functional_specification.strip())
        lines.append("")

        # Technical Requirements
        lines.append("## Technical Requirements")
        lines.append("")
        lines.append("### Architecture")
        lines.append("")
        lines.append(spec_obj.technical_requirements.architecture.strip())
        lines.append("")

        lines.append("### Infrastructure")
        lines.append("")
        lines.append(spec_obj.technical_requirements.infrastructure.strip())
        lines.append("")

        if spec_obj.technical_requirements.impact_analysis:
            lines.append("### Impact Analysis")
            lines.append("")
            lines.append(spec_obj.technical_requirements.impact_analysis.strip())
            lines.append("")

        lines.append("### Target Repositories & Modules")
        for repo in spec_obj.technical_requirements.repositories:
            action_badge = f"`[{repo.action.upper()}]`"
            lines.append(f"#### Repository: `{repo.repo_name}` {action_badge}")
            lines.append("")
            lines.append(repo.instructions.strip())
            lines.append("")

        return "\n".join(lines)
