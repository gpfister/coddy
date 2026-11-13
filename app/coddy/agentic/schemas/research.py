"""Strict Pydantic v2 schemas for research loop outputs (Rule R1).

Defines:
- EpisodeResearchResult (for coding-researcher)
- ResearchClarificationResult (for coding-research-clarifier)
- ResearchReport (for coding-research-reporter)
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.coddy.agentic.schemas.research_plan import (
    ResearchMaterialAssessment,
    ResearchPlanTopic,
    _check_placeholder,
    normalize_research_plan_data,
)


class MermaidDiagram(BaseModel):
    """Mermaid diagram specification representing process flow or call sequence."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="Title of the diagram.")
    diagram_type: str = Field(
        default="flowchart",
        description="Type of Mermaid diagram (e.g. 'flowchart TD', 'sequenceDiagram', 'stateDiagram').",
    )
    code: str = Field(
        description="Valid Mermaid diagram definition syntax (without enclosing markdown code fences).",
    )
    description: str = Field(
        default="",
        description="Plain English explanation of what this diagram depicts, key paths, and behaviors.",
    )

    @field_validator("title", "code")
    @classmethod
    def validate_not_placeholder(cls, v: str, info) -> str:
        return _check_placeholder(v, info.field_name)


class TechnicalAlternative(BaseModel):
    """Candidate technical option, trade-offs, and evaluation criteria."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Name or title of the alternative.")
    description: str = Field(description="Detailed description of the technical alternative.")
    pros: list[str] = Field(default_factory=list, description="List of technical pros and benefits.")
    cons: list[str] = Field(default_factory=list, description="List of technical cons, drawbacks, or risks.")
    recommendation: str = Field(
        default="",
        description="Whether this alternative is recommended or rejected, with supporting rationale.",
    )

    @field_validator("name", "description")
    @classmethod
    def validate_not_placeholder(cls, v: str, info) -> str:
        return _check_placeholder(v, info.field_name)


class CodeImpactReference(BaseModel):
    """Identifies a source code location, file, or symbol impacted by the research subject."""

    model_config = ConfigDict(extra="forbid")

    file_path: str = Field(description="Path to the repository file impacted or consulted.")
    symbol_name: str = Field(
        default="",
        description="Function, class, method, or constant name (or empty string if file-level).",
    )
    description: str = Field(
        description="Explanation of what this code currently does and how it relates to the subject.",
    )
    impact_type: str = Field(
        default="inspect",
        description="Type of impact (e.g. 'modify', 'extend', 'deprecate', 'call', 'inspect').",
    )

    @field_validator("file_path", "description")
    @classmethod
    def validate_not_placeholder(cls, v: str, info) -> str:
        return _check_placeholder(v, info.field_name)


class ProcessLogicDescription(BaseModel):
    """Plain English description of current implementation logic, workflows, and invariants."""

    model_config = ConfigDict(extra="forbid")

    subsystem: str = Field(description="Subsystem, component, or workflow being described.")
    description: str = Field(description="In-depth plain English description of the business/control logic.")
    key_rules: list[str] = Field(
        default_factory=list,
        description="List of invariant business rules, error handling conditions, or validation constraints.",
    )

    @field_validator("subsystem", "description")
    @classmethod
    def validate_not_placeholder(cls, v: str, info) -> str:
        return _check_placeholder(v, info.field_name)


class ResolvedIssue(BaseModel):
    """Represents an open issue resolved either via findings or user clarification."""

    model_config = ConfigDict(extra="forbid")

    issue: str = Field(description="The original open issue or technical uncertainty.")
    resolution: str = Field(description="The concrete resolution, decision, or architectural path chosen.")
    source: Literal["inferred_from_research", "user_clarification"] = Field(
        description="Source of the resolution ('inferred_from_research' or 'user_clarification').",
    )

    @field_validator("issue", "resolution")
    @classmethod
    def validate_not_placeholder(cls, v: str, info) -> str:
        return _check_placeholder(v, info.field_name)


# ---------------------------------------------------------------------------
# 1. Episode Research Result (Worker: coding-researcher)
# ---------------------------------------------------------------------------


class EpisodeResearchResult(BaseModel):
    """Structured output for one research episode (one subject) produced by coding-researcher."""

    model_config = ConfigDict(extra="forbid")

    subject_title: str = Field(description="Title of the research subject investigated in this episode.")
    summary_paragraph: str = Field(
        description="1-paragraph synthesis of what was researched and key findings discovered.",
    )
    summary_bullets: list[str] = Field(
        default_factory=list,
        description="5 to 10 bullet points summarizing key findings (serves as Previous Episode context for next episode).",
    )
    impacted_code_references: list[CodeImpactReference] = Field(
        default_factory=list,
        description="Source code files, symbols, and call sites impacted or analyzed.",
    )
    logic_and_rules_description: str = Field(
        default="",
        description="Plain English description of the current logic, control flow, rules, and constraints.",
    )
    diagrams: list[MermaidDiagram] = Field(
        default_factory=list,
        description="Mermaid diagrams depicting process flowcharts, call sequences, or state transitions.",
    )
    alternatives_and_tradeoffs: list[TechnicalAlternative] = Field(
        default_factory=list,
        description="Candidate technical approaches evaluated, with pros, cons, and recommendations.",
    )
    discovered_apis: list[str] = Field(
        default_factory=list,
        description="Discovered public APIs, interfaces, endpoints, schemas, or tool signatures.",
    )
    open_issues: list[str] = Field(
        default_factory=list,
        description="Concrete technical uncertainties or open questions raised during this episode's research.",
    )

    @field_validator("subject_title", "summary_paragraph")
    @classmethod
    def validate_not_placeholder(cls, v: str, info) -> str:
        return _check_placeholder(v, info.field_name)


# ---------------------------------------------------------------------------
# 2. Research Clarification Result (Worker: coding-research-clarifier)
# ---------------------------------------------------------------------------


class ResearchClarificationResult(BaseModel):
    """Structured output from coding-research-clarifier resolving open issues and proposing new research."""

    model_config = ConfigDict(extra="forbid")

    resolved_issues: list[ResolvedIssue] = Field(
        default_factory=list,
        description="List of all open issues that were resolved (either from findings or user clarification).",
    )
    new_research_topics: list[ResearchPlanTopic] = Field(
        default_factory=list,
        description="New research topics and subjects to add to the research plan when internet research was selected.",
    )


# ---------------------------------------------------------------------------
# 3. Final Synthesized Research Report (Worker: coding-research-reporter)
# ---------------------------------------------------------------------------


class ResearchReport(BaseModel):
    """Final comprehensive research report synthesized by coding-research-reporter.

    Designed to serve as the direct foundation for coding-specifier.
    """

    model_config = ConfigDict(extra="forbid")

    executive_summary: str = Field(
        description="Executive summary synthesizing the problem, research scope, and architectural direction.",
    )
    research_scope: list[str] = Field(
        default_factory=list,
        description="List of core architectural domains, subjects, and questions investigated.",
    )
    research_materials_assessment: list[ResearchMaterialAssessment] = Field(
        default_factory=list,
        description="Assessment of ingested research materials and how they constrain the solution.",
    )
    source_code_impact: list[CodeImpactReference] = Field(
        default_factory=list,
        description="Comprehensive inventory of all impacted repository files, symbols, and call sites.",
    )
    current_logic_and_processes: list[ProcessLogicDescription] = Field(
        default_factory=list,
        description="Plain English descriptions of current implementation logic, rules, and workflows.",
    )
    diagrams: list[MermaidDiagram] = Field(
        default_factory=list,
        description="Complete set of process flowcharts and call sequence diagrams.",
    )
    technical_alternatives_and_recommendations: list[TechnicalAlternative] = Field(
        default_factory=list,
        description="Evaluated architectural alternatives with trade-offs, pros/cons, and final recommendations.",
    )
    clarification_log: list[ResolvedIssue] = Field(
        default_factory=list,
        description="Record of all open issues raised, how they were resolved, and user decisions.",
    )

    @field_validator("executive_summary")
    @classmethod
    def validate_not_placeholder(cls, v: str) -> str:
        return _check_placeholder(v, "executive_summary")


# ---------------------------------------------------------------------------
# Normalization Helpers
# ---------------------------------------------------------------------------


def normalize_episode_research_result(data: Any) -> dict[str, Any]:
    """Normalizes raw LLM output into conforming EpisodeResearchResult dictionary."""
    if not isinstance(data, dict):
        return {
            "subject_title": "Research Subject",
            "summary_paragraph": str(data) if data is not None else "",
            "summary_bullets": [],
            "impacted_code_references": [],
            "logic_and_rules_description": "",
            "diagrams": [],
            "alternatives_and_tradeoffs": [],
            "discovered_apis": [],
            "open_issues": [],
        }

    title = str(data.get("subject_title") or data.get("title") or "Research Subject").strip()
    summary_p = str(data.get("summary_paragraph") or data.get("summary") or "").strip()
    raw_bullets = data.get("summary_bullets") or data.get("bullets") or data.get("findings") or []
    bullets = [str(b).strip() for b in raw_bullets if str(b).strip()]

    # References
    raw_refs = data.get("impacted_code_references") or data.get("code_references") or []
    refs: list[dict[str, Any]] = []
    if isinstance(raw_refs, list):
        for r in raw_refs:
            if isinstance(r, str) and r.strip():
                refs.append(
                    {"file_path": r.strip(), "symbol_name": "", "description": "Consulted", "impact_type": "inspect"}
                )
            elif isinstance(r, dict):
                fp = str(r.get("file_path") or r.get("file") or r.get("path") or "").strip()
                if fp:
                    refs.append(
                        {
                            "file_path": fp,
                            "symbol_name": str(r.get("symbol_name") or r.get("symbol") or "").strip(),
                            "description": str(r.get("description") or "Impacted code reference").strip(),
                            "impact_type": str(r.get("impact_type") or "inspect").strip(),
                        }
                    )

    logic_desc = str(data.get("logic_and_rules_description") or data.get("logic") or "").strip()

    # Diagrams
    raw_diagrams = data.get("diagrams") or []
    diagrams: list[dict[str, Any]] = []
    if isinstance(raw_diagrams, list):
        for d in raw_diagrams:
            if isinstance(d, dict):
                code = str(d.get("code") or d.get("mermaid") or "").strip()
                if code:
                    diagrams.append(
                        {
                            "title": str(d.get("title") or "Process Diagram").strip(),
                            "diagram_type": str(d.get("diagram_type") or "flowchart").strip(),
                            "code": code,
                            "description": str(d.get("description") or "").strip(),
                        }
                    )

    # Alternatives
    raw_alts = data.get("alternatives_and_tradeoffs") or data.get("alternatives") or []
    alts: list[dict[str, Any]] = []
    if isinstance(raw_alts, list):
        for a in raw_alts:
            if isinstance(a, dict):
                name = str(a.get("name") or a.get("title") or "").strip()
                desc = str(a.get("description") or "").strip()
                if name:
                    alts.append(
                        {
                            "name": name,
                            "description": desc or name,
                            "pros": [str(p).strip() for p in (a.get("pros") or []) if str(p).strip()],
                            "cons": [str(c).strip() for c in (a.get("cons") or []) if str(c).strip()],
                            "recommendation": str(a.get("recommendation") or "").strip(),
                        }
                    )

    apis = [str(a).strip() for a in (data.get("discovered_apis") or data.get("apis") or []) if str(a).strip()]
    open_issues = [str(i).strip() for i in (data.get("open_issues") or data.get("issues") or []) if str(i).strip()]

    return {
        "subject_title": title,
        "summary_paragraph": summary_p or "Research completed.",
        "summary_bullets": bullets,
        "impacted_code_references": refs,
        "logic_and_rules_description": logic_desc,
        "diagrams": diagrams,
        "alternatives_and_tradeoffs": alts,
        "discovered_apis": apis,
        "open_issues": open_issues,
    }


def normalize_clarification_result(data: Any) -> dict[str, Any]:
    """Normalizes raw LLM output into conforming ResearchClarificationResult dictionary."""
    if not isinstance(data, dict):
        return {"resolved_issues": [], "new_research_topics": []}

    raw_resolved = data.get("resolved_issues") or data.get("resolutions") or []
    resolved: list[dict[str, Any]] = []
    if isinstance(raw_resolved, list):
        for item in raw_resolved:
            if isinstance(item, dict):
                issue = str(item.get("issue") or item.get("question") or "").strip()
                res = str(item.get("resolution") or item.get("answer") or "").strip()
                src = str(item.get("source") or "inferred_from_research").strip().lower()
                if src not in {"inferred_from_research", "user_clarification"}:
                    src = "inferred_from_research"
                if issue and res:
                    resolved.append({"issue": issue, "resolution": res, "source": src})

    raw_topics = data.get("new_research_topics")
    if isinstance(raw_topics, list):
        plan_dict = {"topics": raw_topics}
    elif isinstance(raw_topics, dict):
        plan_dict = raw_topics
    else:
        plan_dict = data
    norm_plan = normalize_research_plan_data(plan_dict)
    new_topics = norm_plan.get("topics", [])

    return {
        "resolved_issues": resolved,
        "new_research_topics": new_topics,
    }


def normalize_research_report_data(data: Any) -> dict[str, Any]:
    """Normalizes raw LLM output into conforming ResearchReport dictionary."""
    if not isinstance(data, dict):
        return {
            "executive_summary": str(data) if data is not None else "Research Report",
            "research_scope": [],
            "research_materials_assessment": [],
            "source_code_impact": [],
            "current_logic_and_processes": [],
            "diagrams": [],
            "technical_alternatives_and_recommendations": [],
            "clarification_log": [],
        }

    exec_summary = str(data.get("executive_summary") or data.get("summary") or "Research Report").strip()
    scope = [str(s).strip() for s in (data.get("research_scope") or data.get("scope") or []) if str(s).strip()]

    # Source code impact
    raw_impact = data.get("source_code_impact") or data.get("impacted_code") or []
    code_impact: list[dict[str, Any]] = []
    if isinstance(raw_impact, list):
        for item in raw_impact:
            if isinstance(item, dict):
                fp = str(item.get("file_path") or item.get("file") or "").strip()
                if fp:
                    code_impact.append(
                        {
                            "file_path": fp,
                            "symbol_name": str(item.get("symbol_name") or item.get("symbol") or "").strip(),
                            "description": str(item.get("description") or "Impacted reference").strip(),
                            "impact_type": str(item.get("impact_type") or "inspect").strip(),
                        }
                    )

    # Logic & processes
    raw_logic = data.get("current_logic_and_processes") or data.get("processes") or []
    logic_list: list[dict[str, Any]] = []
    if isinstance(raw_logic, list):
        for item in raw_logic:
            if isinstance(item, dict):
                sub = str(item.get("subsystem") or item.get("name") or "Core").strip()
                desc = str(item.get("description") or "").strip()
                if desc:
                    logic_list.append(
                        {
                            "subsystem": sub,
                            "description": desc,
                            "key_rules": [
                                str(r).strip()
                                for r in (item.get("key_rules") or item.get("rules") or [])
                                if str(r).strip()
                            ],
                        }
                    )

    # Diagrams
    raw_diagrams = data.get("diagrams") or []
    diagrams: list[dict[str, Any]] = []
    if isinstance(raw_diagrams, list):
        for d in raw_diagrams:
            if isinstance(d, dict):
                code = str(d.get("code") or "").strip()
                if code:
                    diagrams.append(
                        {
                            "title": str(d.get("title") or "Architecture Diagram").strip(),
                            "diagram_type": str(d.get("diagram_type") or "flowchart").strip(),
                            "code": code,
                            "description": str(d.get("description") or "").strip(),
                        }
                    )

    # Alternatives
    raw_alts = data.get("technical_alternatives_and_recommendations") or data.get("alternatives") or []
    alts: list[dict[str, Any]] = []
    if isinstance(raw_alts, list):
        for a in raw_alts:
            if isinstance(a, dict):
                name = str(a.get("name") or "").strip()
                desc = str(a.get("description") or "").strip()
                if name:
                    alts.append(
                        {
                            "name": name,
                            "description": desc or name,
                            "pros": [str(p).strip() for p in (a.get("pros") or []) if str(p).strip()],
                            "cons": [str(c).strip() for c in (a.get("cons") or []) if str(c).strip()],
                            "recommendation": str(a.get("recommendation") or "").strip(),
                        }
                    )

    # Clarification log
    raw_log = data.get("clarification_log") or data.get("resolved_issues") or []
    clarification_log: list[dict[str, Any]] = []
    if isinstance(raw_log, list):
        for item in raw_log:
            if isinstance(item, dict):
                iss = str(item.get("issue") or "").strip()
                res = str(item.get("resolution") or "").strip()
                src = str(item.get("source") or "inferred_from_research").strip().lower()
                if src not in {"inferred_from_research", "user_clarification"}:
                    src = "inferred_from_research"
                if iss and res:
                    clarification_log.append({"issue": iss, "resolution": res, "source": src})

    return {
        "executive_summary": exec_summary,
        "research_scope": scope,
        "research_materials_assessment": [],
        "source_code_impact": code_impact,
        "current_logic_and_processes": logic_list,
        "diagrams": diagrams,
        "technical_alternatives_and_recommendations": alts,
        "clarification_log": clarification_log,
    }


normalize_episode_research_data = normalize_episode_research_result
normalize_research_clarification_data = normalize_clarification_result

__all__ = [
    "CodeImpactReference",
    "EpisodeResearchResult",
    "MermaidDiagram",
    "ProcessLogicDescription",
    "ResearchClarificationResult",
    "ResearchReport",
    "ResolvedIssue",
    "TechnicalAlternative",
    "normalize_clarification_result",
    "normalize_episode_research_data",
    "normalize_episode_research_result",
    "normalize_research_clarification_data",
    "normalize_research_report_data",
]
