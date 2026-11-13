# Artifact Mappers (Rule R2)

## 1. The Mapping Requirement
Rule R2 states:
> *For every JSON artifact generated, the system must automatically invoke a **Mapper** utility to generate a human-readable `.md` (Markdown) file for user review.*

While LLMs and internal agent state operate reliably on structured, strongly-typed JSON data trees, software developers, architects, and product managers require readable Markdown documentation for code reviews, pull requests, and architecture reviews.

The Mapper layer guarantees:
1. **Zero Information Loss**: Every entity, property, and instruction in the JSON representation is mapped to a Markdown heading, table, or code block.
2. **Automated Dual-Artifact Persistence**:
   - `.coddy/specifications/<project>_spec.json` $\leftrightarrow$ `.coddy/specifications/<project>_spec.md`
   - `.coddy/plans/<project>_plan.json` $\leftrightarrow$ `.coddy/plans/<project>_plan.md`

## 2. Specification Mapper
Implemented in `app/coddy/mappers/spec_mapper.py`:
- Maps executive brief, goals, target KPIs.
- Translates business and compliance rules into a structured policy table with status badges (`NEW`, `UPDATED`, `EXISTING`, `BYPASSED`).
- Renders expanded use cases with full flow narratives and edge conditions.
- Compiles validation test matrices.
- Translates architecture, infrastructure, and repository instructions with action flags (`[CREATE]`, `[CHANGE]`, `[REMOVE]`).

## 3. Plan Mapper
Implemented in `app/coddy/mappers/plan_mapper.py`:
- Calculates plan metrics (total tiers, steps, and tasks).
- Renders hierarchical headings (`Tier` $\rightarrow$ `Step` $\rightarrow$ `Task`).
- Displays concurrency execution tags (`Sequential` vs `Parallel`).
- Renders interactive markdown task checkboxes (`[ ]` / `[x]`) alongside status badges.
