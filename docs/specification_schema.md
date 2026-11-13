# Specification Schema Reference

The `SPECIFICATION` schema represents the structural truth of project and feature requirements in Coddy. It supports both whole-project kickoffs and feature lifecycle specifications (adding, modifying, or removing a feature). Any extra or unrecognized fields are strictly forbidden (`extra="forbid"`).

## JSON Schema Definition

```json
{
  "version": "1.0",
  "metadata": {
    "project_name": "string",
    "spec_type": "project_kickoff | feature_add | feature_modify | feature_remove",
    "feature_name": "string (optional)",
    "timestamp": "ISO-8601"
  },
  "executive_brief": "A single paragraph summary for executive teams.",
  "business_requirements": {
    "goals": ["string"],
    "target_kpis": ["string"],
    "rules": [
      {
        "rule_text": "string",
        "type": "new | updated | existing | bypassed"
      }
    ],
    "use_cases": [
      {
        "id": "uc_01",
        "title": "string",
        "content": "Detailed expansion of the use case..."
      }
    ],
    "test_cases": [
      {
        "id": "tc_01",
        "test_description": "string",
        "expected_outcome": "string"
      }
    ]
  },
  "functional_specification": "Full documentation of processes, workflow, and logic.",
  "technical_requirements": {
    "architecture": "Detailed description of the solution and software architecture.",
    "infrastructure": "Detailed instructions for infrastructure to build/change/remove.",
    "repositories": [
      {
        "repo_name": "string",
        "action": "create | change | remove",
        "instructions": "Detailed technical instructions."
      }
    ],
    "impact_analysis": "Detailed breaking changes, migration, or deprecation/removal analysis (optional)."
  }
}
```

## Field Dictionary

| Path | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `version` | `string` | Must be `"1.0"` | Schema version identifier |
| `metadata.project_name` | `string` | Non-empty | Unique project/system name |
| `metadata.spec_type` | `enum` | `project_kickoff`, `feature_add`, `feature_modify`, `feature_remove` | Lifecycle scope (defaults to `project_kickoff`) |
| `metadata.feature_name` | `string` | Optional | Name of targeted feature for feature-scoped specs |
| `metadata.timestamp` | `string` | ISO-8601 | Generation timestamp |
| `executive_brief` | `string` | Single paragraph | Executive summary |
| `business_requirements.goals` | `list[string]` | $\ge 1$ item | High-level business goals |
| `business_requirements.target_kpis` | `list[string]` | $\ge 1$ item | Measurable KPIs |
| `business_requirements.rules[].type` | `enum` | `new`, `updated`, `existing`, `bypassed` | Rule classification |
| `business_requirements.use_cases[].content`| `string` | Fully expanded | Detailed narrative with flows & edge cases |
| `technical_requirements.repositories[].action` | `enum` | `create`, `change`, `remove` | Action to take on repo |
| `technical_requirements.impact_analysis` | `string` | Optional | Impact, migration, breaking change, or deprecation analysis |
