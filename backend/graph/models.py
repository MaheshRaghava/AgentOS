from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, TypedDict
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING  = "pending"
    RUNNING  = "running"
    DONE     = "done"
    FAILED   = "failed"
    SKIPPED  = "skipped"


class WorkerType(str, Enum):
    RESEARCHER  = "researcher"
    CODER       = "coder"
    SUMMARIZER  = "summarizer"
    BROWSER     = "browser"
    SYNTHESIZER = "synthesizer"


class Task(BaseModel):
    id: str          = Field(default_factory=lambda: uuid4().hex[:8])
    name: str
    description: str
    worker: WorkerType
    dependencies: list[str] = Field(default_factory=list)

    status:      TaskStatus      = TaskStatus.PENDING
    retry_count: int             = 0
    max_retries: int             = 3
    output:      str | None      = None
    error:       str | None      = None
    started_at:  datetime | None = None
    finished_at: datetime | None = None

    def is_ready(self, completed_ids: set[str]) -> bool:
        return all(dep in completed_ids for dep in self.dependencies)


class RunStatus(str, Enum):
    PLANNING  = "planning"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


class Run(BaseModel):
    id:           str        = Field(default_factory=lambda: uuid4().hex)
    goal:         str
    status:       RunStatus  = RunStatus.PLANNING
    tasks:        list[Task] = Field(default_factory=list)
    final_output: str | None = None
    created_at:   datetime   = Field(default_factory=datetime.utcnow)
    finished_at:  datetime | None = None


class GoalRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=1000)


class GoalResponse(BaseModel):
    run_id:  str = ""
    message: str = "Run started"


class HealthResponse(BaseModel):
    status:  str = "ok"
    version: str = "0.1.0"


class WSEventType(str, Enum):
    TASK_UPDATE  = "task_update"
    LOG_LINE     = "log_line"
    FINAL_OUTPUT = "final_output"
    ERROR        = "error"


class WSEvent(BaseModel):
    event:  WSEventType
    run_id: str
    data:   dict[str, Any]


# ---------------------------------------------------------------------------
# LangGraph requires a TypedDict as its state schema
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    run_id:       str               # which run this state belongs to
    goal:         str               # original user goal
    tasks:        list[dict]        # serialized Task dicts (JSON-safe for LangGraph)
    completed:    list[str]         # task ids that finished successfully
    failed:       list[str]         # task ids that permanently failed
    outputs:      dict[str, str]    # task_id → output string
    final_output: str               # synthesized final answer
    error:        str               # run-level error message if any
