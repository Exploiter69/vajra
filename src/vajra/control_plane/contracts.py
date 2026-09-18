from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ControlCommand(str, Enum):
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    ABORT = "abort"
    RETRY = "retry"
    APPROVE = "approve"
    REJECT = "reject"


@dataclass(frozen=True)
class ControlResult:
    command_id: str
    run_id: str | None
    accepted: bool
    state: str | None
    message: str


@dataclass(frozen=True)
class ScheduleSpec:
    schedule_id: str
    due_at: str
    job_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    interval_seconds: int | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.schedule_id.strip():
            raise ValueError("schedule_id must be nonempty")
        if not self.job_type.strip():
            raise ValueError("job_type must be nonempty")
        if self.interval_seconds is not None and self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
