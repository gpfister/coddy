"""Deterministic Markdown mapper for ResearchPlan structured output (Rule R2)."""

from app.coddy.agentic.schemas.research_plan import ResearchPlan


class ResearchPlanMapper:
    """Transforms a ResearchPlan structured instance into human-readable Markdown."""

    @staticmethod
    def to_markdown(plan: ResearchPlan) -> str:
        """Converts a ResearchPlan into human-readable Markdown."""
        parts: list[str] = [
            "# RESEARCH PLAN",
            "",
        ]

        if plan.rationale:
            parts.extend(
                [
                    "## Rationale & Architectural Decomposition",
                    "",
                    plan.rationale.strip(),
                    "",
                ]
            )

        if plan.user_request_summary or plan.user_request_bullets:
            parts.extend(["## Context Summaries for Episodic Research", "", "### User Request Context", ""])
            if plan.user_request_summary:
                parts.append(f"{plan.user_request_summary.strip()}\n")
            if plan.user_request_bullets:
                for b in plan.user_request_bullets:
                    parts.append(f"- {b}")
                parts.append("")

        if plan.project_context_summary or plan.project_context_bullets:
            parts.extend(["### Project Architecture Context", ""])
            if plan.project_context_summary:
                parts.append(f"{plan.project_context_summary.strip()}\n")
            if plan.project_context_bullets:
                for b in plan.project_context_bullets:
                    parts.append(f"- {b}")
                parts.append("")

        if plan.research_materials:
            parts.extend(
                [
                    "## Research Materials Assessment",
                    "",
                ]
            )
            for m_idx, mat in enumerate(plan.research_materials, start=1):
                parts.append(f"### Material {m_idx}: `{mat.file_path}`")
                parts.append(f"**Served Information**:\n{mat.served_information.strip()}\n")
                parts.append(f"**Code/Documentation Investigation Targets**:\n{mat.investigation_targets.strip()}\n")
                web_needed = "Yes" if mat.requires_internet_research else "No"
                parts.append(f"**Requires External Web Research**: {web_needed}")
                if mat.internet_research_rationale:
                    parts.append(f"*Web Research Rationale*: {mat.internet_research_rationale.strip()}\n")
                else:
                    parts.append("")
                parts.append("---")
                parts.append("")

        if not plan.topics:
            parts.append("*(No research topics identified)*")
            return "\n".join(parts)

        parts.extend(
            [
                "## Research Topics & Subjects",
                "",
            ]
        )

        for t_idx, topic in enumerate(plan.topics, start=1):
            parts.append(f"### Topic {t_idx}: {topic.topic}")
            if topic.description:
                parts.append(f"\n{topic.description.strip()}\n")
            else:
                parts.append("")

            if not topic.subjects:
                parts.append("*(No specific subjects under this topic)*\n")
                continue

            parts.append("#### Subjects to Research\n")
            for s_idx, subject in enumerate(topic.subjects, start=1):
                sources_str = ", ".join(f"`{src}`" for src in subject.target_sources)
                parts.append(f"##### {t_idx}.{s_idx} {subject.title}")
                parts.append(f"**Target Sources**: {sources_str}\n")
                parts.append(f"{subject.description.strip()}\n")

                if subject.open_issues:
                    parts.append("**Open Issues to Resolve:**")
                    for issue in subject.open_issues:
                        parts.append(f"- {issue}")
                    parts.append("")

                if subject.approaches:
                    parts.append("**Candidate Technical Approaches:**")
                    for approach in subject.approaches:
                        parts.append(f"- **{approach.name}**: {approach.description}")
                        if approach.rationale:
                            parts.append(f"  *Evaluation Criteria / Rationale*: {approach.rationale}")
                    parts.append("")

                if subject.directions:
                    parts.append("**Research Directions & Expected Deliverables:**")
                    for direction in subject.directions:
                        parts.append(f"- {direction}")
                    parts.append("")

            parts.append("---")
            parts.append("")

        return "\n".join(parts).strip() + "\n"
