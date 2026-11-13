"""Plan Mapper: JSON -> Markdown.

Enforces Rule R2: The Mapping Requirement.
Translates strictly validated JSON Execution Plan into hierarchical Markdown.
"""

from app.coddy.agentic.schemas.plan import Plan


class PlanMapper:
    """Transforms a Plan schema instance into a human-readable hierarchical Markdown plan."""

    @classmethod
    def to_markdown(cls, plan: Plan | dict) -> str:
        if isinstance(plan, dict):
            plan_obj = Plan.model_validate(plan)
        else:
            plan_obj = plan

        lines: list[str] = []

        # Header & Metadata
        lines.append(f"# Execution Plan: {plan_obj.metadata.project_id}")
        lines.append("")
        lines.append(f"**Version**: `{plan_obj.version}`  ")
        lines.append(f"**Specification Reference**: `{plan_obj.metadata.spec_reference_id}`  ")
        lines.append(f"**Timestamp**: `{plan_obj.metadata.timestamp}`  ")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Metrics / Overview
        total_tiers = len(plan_obj.structure.tiers)
        total_steps = sum(len(tier.steps) for tier in plan_obj.structure.tiers)
        total_tasks = sum(len(step.tasks) for tier in plan_obj.structure.tiers for step in tier.steps)

        lines.append("## Plan Overview")
        lines.append("")
        lines.append(f"- **Tiers**: {total_tiers}")
        lines.append(f"- **Steps**: {total_steps}")
        lines.append(f"- **Tasks**: {total_tasks}")
        lines.append("")

        # Hierarchical breakdown
        lines.append("## Execution Breakdown")
        lines.append("")

        for tier in plan_obj.structure.tiers:
            lines.append(f"### Tier `{tier.tier_id}`: {tier.title}")
            lines.append("")

            for step in tier.steps:
                concurrency_badge = f"*{step.type.capitalize()} Execution*"
                lines.append(f"#### Step `{step.step_id}` ({concurrency_badge})")
                lines.append("")

                for task in step.tasks:
                    status_badge = "[x]" if task.status == "completed" else "[ ]"
                    status_tag = f"`{task.status.upper()}`"
                    lines.append(f"##### {status_badge} `{task.task_id}`: {task.label} ({status_tag})")
                    lines.append("")
                    lines.append("**Instructions:**")
                    lines.append("")
                    lines.append(task.instructions.strip())
                    lines.append("")

        return "\n".join(lines)
