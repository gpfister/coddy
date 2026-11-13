"""Strict Pydantic schema for Coddy Plan artifacts.

Enforces Rule R1: The Structured Output Mandate (extra='forbid').
Maintains a hard link to project and specification metadata.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    """Base model forbidding unexpected keys."""

    model_config = ConfigDict(extra="forbid")


class PlanMetadata(StrictBaseModel):
    """Metadata linking the plan to project and specification."""

    project_id: str = Field(..., description="Project identifier")
    spec_reference_id: str = Field(..., description="Reference link or hash to specification JSON")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO-8601 formatted timestamp",
    )


class TaskItem(StrictBaseModel):
    """Individual execution task within a step."""

    task_id: str = Field(..., description="Unique task identifier (e.g. TASK_01)")
    label: str = Field(..., description="Short task name")
    status: Literal["pending", "completed"] = Field(default="pending", description="Task execution status")
    instructions: str = Field(..., description="Detailed execution steps for this specific task")


class StepItem(StrictBaseModel):
    """Execution step containing one or more tasks."""

    step_id: str = Field(..., description="Unique step identifier (e.g. S1_1)")
    type: Literal["sequential", "parallel"] = Field(..., description="Execution concurrency type")
    tasks: list[TaskItem] = Field(..., min_length=1, description="List of tasks")


class TierItem(StrictBaseModel):
    """Hierarchical tier grouping steps."""

    tier_id: str = Field(..., description="Unique tier identifier (e.g. T1)")
    title: str = Field(..., description="Tier name")
    steps: list[StepItem] = Field(..., min_length=1, description="List of steps")


class PlanStructure(StrictBaseModel):
    """Container for hierarchical tiers."""

    tiers: list[TierItem] = Field(..., min_length=1, description="Ordered tiers of execution")


class Plan(StrictBaseModel):
    """Root Plan artifact.

    Must strictly match the Coddy PLAN JSON schema.
    """

    version: Literal["1.0"] = Field(default="1.0", description="Schema version")
    metadata: PlanMetadata = Field(..., description="Metadata and specification reference")
    structure: PlanStructure = Field(..., description="Hierarchical plan tiers and tasks")


def normalize_plan_data(
    raw: dict,
    default_project_id: str = "project",
    default_spec_ref: str = "specification.json",
) -> dict:
    """Normalizes arbitrary or loosely-structured LLM JSON output into a strictly valid Plan schema dict.

    Handles common LLM deviations:
    - Root-level placement of tiers or tasks.
    - Missing metadata or spec_reference_id.
    - Missing or alternative field names (e.g. name instead of label/title, description instead of instructions).
    - Forbidden extra fields removed to satisfy Rule R1 (extra='forbid').
    """
    version = "1.0"

    # Metadata
    meta_raw = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    project_id = str(meta_raw.get("project_id") or raw.get("project_id") or default_project_id).strip() or "project"
    spec_ref = (
        str(meta_raw.get("spec_reference_id") or raw.get("spec_reference_id") or default_spec_ref).strip()
        or "specification.json"
    )
    timestamp = str(meta_raw.get("timestamp") or datetime.now(UTC).isoformat())

    metadata = {
        "project_id": project_id,
        "spec_reference_id": spec_ref,
        "timestamp": timestamp,
    }

    # Structure & Tiers
    struct_raw = raw.get("structure") if isinstance(raw.get("structure"), dict) else {}
    raw_tiers = struct_raw.get("tiers") or raw.get("tiers") or raw.get("plan") or []
    if not isinstance(raw_tiers, list):
        raw_tiers = [raw_tiers] if raw_tiers else []

    tiers = []
    for t_idx, tier in enumerate(raw_tiers):
        if isinstance(tier, dict):
            t_id = tier.get("tier_id") or tier.get("id") or f"T{t_idx + 1}"
            title = tier.get("title") or tier.get("name") or f"Tier {t_idx + 1}: Execution Phase"

            raw_steps = tier.get("steps") or []
            if not isinstance(raw_steps, list):
                raw_steps = [raw_steps] if raw_steps else []

            steps = []
            for s_idx, step in enumerate(raw_steps):
                if isinstance(step, dict):
                    s_id = step.get("step_id") or step.get("id") or f"S{t_idx + 1}_{s_idx + 1}"
                    s_type = str(step.get("type", "sequential")).lower().strip()
                    if s_type not in ("sequential", "parallel"):
                        s_type = "sequential"

                    raw_tasks = step.get("tasks") or []
                    if not isinstance(raw_tasks, list):
                        raw_tasks = [raw_tasks] if raw_tasks else []

                    tasks = []
                    for k_idx, task in enumerate(raw_tasks):
                        if isinstance(task, dict):
                            task_id = (
                                task.get("task_id") or task.get("id") or f"TASK_{t_idx + 1}_{s_idx + 1}_{k_idx + 1:02d}"
                            )
                            label = task.get("label") or task.get("name") or task.get("title") or f"Task {k_idx + 1}"
                            status = str(task.get("status", "pending")).lower().strip()
                            if status not in ("pending", "completed"):
                                status = "pending"
                            instructions = (
                                task.get("instructions")
                                or task.get("description")
                                or task.get("details")
                                or f"Execute implementation tasks for {label}."
                            )
                            tasks.append(
                                {
                                    "task_id": str(task_id).strip(),
                                    "label": str(label).strip(),
                                    "status": status,
                                    "instructions": str(instructions).strip(),
                                }
                            )
                        elif task:
                            tasks.append(
                                {
                                    "task_id": f"TASK_{t_idx + 1}_{s_idx + 1}_{k_idx + 1:02d}",
                                    "label": str(task).strip(),
                                    "status": "pending",
                                    "instructions": f"Execute implementation tasks for {task}.",
                                }
                            )
                    if not tasks:
                        tasks = [
                            {
                                "task_id": f"TASK_{t_idx + 1}_{s_idx + 1}_01",
                                "label": f"Step {s_idx + 1} Implementation",
                                "status": "pending",
                                "instructions": "Execute required step actions.",
                            }
                        ]
                    steps.append({"step_id": str(s_id).strip(), "type": s_type, "tasks": tasks})
                elif step:
                    steps.append(
                        {
                            "step_id": f"S{t_idx + 1}_{s_idx + 1}",
                            "type": "sequential",
                            "tasks": [
                                {
                                    "task_id": f"TASK_{t_idx + 1}_{s_idx + 1}_01",
                                    "label": str(step).strip(),
                                    "status": "pending",
                                    "instructions": f"Implement {step}.",
                                }
                            ],
                        }
                    )
            if not steps:
                steps = [
                    {
                        "step_id": f"S{t_idx + 1}_1",
                        "type": "sequential",
                        "tasks": [
                            {
                                "task_id": f"TASK_{t_idx + 1}_1_01",
                                "label": f"{title} Implementation",
                                "status": "pending",
                                "instructions": f"Execute implementation tasks for {title}.",
                            }
                        ],
                    }
                ]
            tiers.append({"tier_id": str(t_id).strip(), "title": str(title).strip(), "steps": steps})
        elif tier:
            tiers.append(
                {
                    "tier_id": f"T{t_idx + 1}",
                    "title": str(tier).strip(),
                    "steps": [
                        {
                            "step_id": f"S{t_idx + 1}_1",
                            "type": "sequential",
                            "tasks": [
                                {
                                    "task_id": f"TASK_{t_idx + 1}_1_01",
                                    "label": f"{tier} Task",
                                    "status": "pending",
                                    "instructions": f"Implement {tier}.",
                                }
                            ],
                        }
                    ],
                }
            )

    if not tiers:
        tiers = [
            {
                "tier_id": "T1",
                "title": "Foundation & Setup",
                "steps": [
                    {
                        "step_id": "S1_1",
                        "type": "sequential",
                        "tasks": [
                            {
                                "task_id": "TASK_01",
                                "label": "Initialize System",
                                "status": "pending",
                                "instructions": "Set up core architecture and baseline configuration.",
                            }
                        ],
                    }
                ],
            }
        ]

    return {
        "version": version,
        "metadata": metadata,
        "structure": {"tiers": tiers},
    }
