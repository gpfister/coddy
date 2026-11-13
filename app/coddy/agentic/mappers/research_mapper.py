"""Deterministic Markdown mappers for EpisodeResearchResult and ResearchReport (Rule R2)."""

from app.coddy.agentic.schemas.research import (
    EpisodeResearchResult,
    ResearchReport,
)


class EpisodeResearchMapper:
    """Transforms an EpisodeResearchResult into human-readable Markdown."""

    @staticmethod
    def to_markdown(result: EpisodeResearchResult) -> str:
        """Converts an EpisodeResearchResult into Markdown."""
        parts: list[str] = [
            f"# RESEARCH EPISODE: {result.subject_title.upper()}",
            "",
            "## Summary of Findings",
            "",
            result.summary_paragraph.strip(),
            "",
        ]

        if result.summary_bullets:
            parts.append("### Key Findings")
            for b in result.summary_bullets:
                parts.append(f"- {b}")
            parts.append("")

        if result.impacted_code_references:
            parts.extend(["## Impacted Code References", ""])
            for ref in result.impacted_code_references:
                sym_str = f" (`{ref.symbol_name}`)" if ref.symbol_name else ""
                parts.append(f"- **`{ref.file_path}`**{sym_str} [{ref.impact_type.upper()}]: {ref.description}")
            parts.append("")

        if result.logic_and_rules_description:
            parts.extend(
                [
                    "## Current Logic & Workflow Rules",
                    "",
                    result.logic_and_rules_description.strip(),
                    "",
                ]
            )

        if result.diagrams:
            parts.extend(["## Architectural & Process Diagrams", ""])
            for diag in result.diagrams:
                parts.append(f"### {diag.title}")
                if diag.description:
                    parts.append(f"\n{diag.description.strip()}\n")
                parts.append(f"```{diag.diagram_type}")
                parts.append(diag.code.strip())
                parts.append("```\n")

        if result.alternatives_and_tradeoffs:
            parts.extend(["## Technical Alternatives & Trade-offs", ""])
            for alt in result.alternatives_and_tradeoffs:
                parts.append(f"### Option: {alt.name}")
                parts.append(f"{alt.description.strip()}\n")
                if alt.pros:
                    parts.append("**Pros:**")
                    for p in alt.pros:
                        parts.append(f"- [x] {p}")
                    parts.append("")
                if alt.cons:
                    parts.append("**Cons:**")
                    for c in alt.cons:
                        parts.append(f"- [ ] {c}")
                    parts.append("")
                if alt.recommendation:
                    parts.append(f"**Recommendation**: {alt.recommendation.strip()}\n")

        if result.discovered_apis:
            parts.extend(["## Discovered APIs & Contracts", ""])
            for api in result.discovered_apis:
                parts.append(f"- `{api}`")
            parts.append("")

        if result.open_issues:
            parts.extend(["## Open Issues Raised", ""])
            for issue in result.open_issues:
                parts.append(f"- [ ] {issue}")
            parts.append("")

        return "\n".join(parts).strip() + "\n"


class ResearchReportMapper:
    """Transforms a comprehensive ResearchReport into the definitive RESEARCH_REPORT.md document."""

    @staticmethod
    def to_markdown(report: ResearchReport) -> str:
        """Converts a ResearchReport into a structured 6-section Markdown document."""
        parts: list[str] = [
            "# TECHNICAL RESEARCH REPORT",
            "",
            "## 1. Executive Summary & Research Scope",
            "",
            report.executive_summary.strip(),
            "",
        ]

        if report.research_scope:
            parts.append("### Research Scope & Focus Areas")
            for scope in report.research_scope:
                parts.append(f"- {scope}")
            parts.append("")

        parts.extend(["---", "", "## 2. Research Materials Ingestion & Assessment", ""])
        if report.research_materials_assessment:
            for idx, mat in enumerate(report.research_materials_assessment, start=1):
                parts.append(f"### Material {idx}: `{mat.file_path}`")
                parts.append(f"**Served Information**:\n{mat.served_information.strip()}\n")
                parts.append(f"**Code Investigation Targets**:\n{mat.investigation_targets.strip()}\n")
                net_req = "Yes" if mat.requires_internet_research else "No"
                parts.append(f"**Required Internet Research**: {net_req}")
                if mat.internet_research_rationale:
                    parts.append(f"*Rationale*: {mat.internet_research_rationale.strip()}\n")
                else:
                    parts.append("")
        else:
            parts.append("*(No external research materials ingested for this session)*\n")

        parts.extend(["---", "", "## 3. Source Code Impact Analysis", ""])
        if report.source_code_impact:
            parts.extend(
                [
                    "| File Path | Symbol / Entity | Impact Type | Description |",
                    "| :--- | :--- | :--- | :--- |",
                ]
            )
            for ref in report.source_code_impact:
                sym = f"`{ref.symbol_name}`" if ref.symbol_name else "*(file)*"
                clean_desc = ref.description.replace("|", "/")
                parts.append(f"| `{ref.file_path}` | {sym} | `{ref.impact_type}` | {clean_desc} |")
            parts.append("")
        else:
            parts.append("*(No specific source code files marked for impact)*\n")

        parts.extend(["---", "", "## 4. Current Logic & Process Implementations", ""])
        if report.current_logic_and_processes:
            for proc in report.current_logic_and_processes:
                parts.append(f"### Subsystem: {proc.subsystem}")
                parts.append(f"\n{proc.description.strip()}\n")
                if proc.key_rules:
                    parts.append("**Invariant Rules & Constraints:**")
                    for rule in proc.key_rules:
                        parts.append(f"- {rule}")
                    parts.append("")
        else:
            parts.append("*(Current logic details synthesized directly into diagrams)*\n")

        if report.diagrams:
            parts.append("### Process & Call Sequence Diagrams\n")
            for diag in report.diagrams:
                parts.append(f"#### {diag.title}")
                if diag.description:
                    parts.append(f"\n{diag.description.strip()}\n")
                parts.append(f"```{diag.diagram_type}")
                parts.append(diag.code.strip())
                parts.append("```\n")

        parts.extend(["---", "", "## 5. Technical Alternatives, Trade-offs & Recommendations", ""])
        if report.technical_alternatives_and_recommendations:
            for alt in report.technical_alternatives_and_recommendations:
                parts.append(f"### Alternative: {alt.name}")
                parts.append(f"{alt.description.strip()}\n")
                if alt.pros:
                    parts.append("**Pros:**")
                    for p in alt.pros:
                        parts.append(f"- [x] {p}")
                    parts.append("")
                if alt.cons:
                    parts.append("**Cons:**")
                    for c in alt.cons:
                        parts.append(f"- [ ] {c}")
                    parts.append("")
                if alt.recommendation:
                    parts.append(f"**Technical Recommendation**: {alt.recommendation.strip()}\n")
        else:
            parts.append("*(Direct implementation path confirmed; no competing alternatives)*\n")

        parts.extend(["---", "", "## 6. Clarification Log & Resolved Decisions", ""])
        if report.clarification_log:
            for item in report.clarification_log:
                src_badge = "User Clarified" if item.source == "user_clarification" else "Inferred from Code/Docs"
                parts.append(f"- **Issue**: {item.issue}")
                parts.append(f"  - **Resolution** [{src_badge}]: {item.resolution}")
            parts.append("")
        else:
            parts.append("*(No unresolved issues required clarification during research)*\n")

        return "\n".join(parts).strip() + "\n"
