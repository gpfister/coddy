# Plan Schema Reference

The `PLAN` schema represents the structural truth of the execution hierarchy. It maintains a hard link to the specification metadata and decomposes execution into ordered Tiers, Steps, and Tasks.

## JSON Schema Definition

```json
{
  "version": "1.0",
  "metadata": {
    "project_id": "string",
    "spec_reference_id": "link_to_specification_json",
    "timestamp": "ISO-8601"
  },
  "structure": {
    "tiers": [
      {
        "tier_id": "T1",
        "title": "Tier Name",
        "steps": [
          {
            "step_id": "S1_1",
            "type": "sequential | parallel",
            "tasks": [
              {
                "task_id": "TASK_01",
                "label": "Task Name",
                "status": "pending | completed",
                "instructions": "Detailed execution steps for this specific task."
              }
            ]
          }
        ]
      }
    ]
  }
}
```

## Field Dictionary

| Path | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `version` | `string` | Must be `"1.0"` | Schema version identifier |
| `metadata.project_id` | `string` | Non-empty | Target project identifier |
| `metadata.spec_reference_id` | `string` | Path or ID | Link to approved specification |
| `structure.tiers[].tier_id` | `string` | e.g. `T1`, `T2` | Unique tier identifier |
| `structure.tiers[].steps[].type` | `enum` | `sequential`, `parallel` | Step concurrency mode |
| `structure.tiers[].steps[].tasks[].status` | `enum` | `pending`, `completed` | Task execution state |
| `structure.tiers[].steps[].tasks[].instructions` | `string` | Fully expanded | Step-by-step developer instructions |
