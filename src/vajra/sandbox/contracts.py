from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SandboxSpec:
    """Immutable authority boundary requested for a sandbox."""

    workspace_id: str
    filesystem_scope: tuple[str, ...] = ()
    network_enabled: bool = False
    allowed_capabilities: tuple[str, ...] = ()
    resource_limits: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.workspace_id:
            raise ValueError("workspace_id must not be empty")


@dataclass(frozen=True)
class SandboxHandle:
    """Opaque identity for a live sandbox instance."""

    sandbox_id: str
    backend: str

    def __post_init__(self) -> None:
        if not self.sandbox_id:
            raise ValueError("sandbox_id must not be empty")
        if not self.backend:
            raise ValueError("backend must not be empty")


@dataclass(frozen=True)
class SandboxExecution:
    """Backend-neutral report about sandbox execution."""

    sandbox_id: str
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.sandbox_id:
            raise ValueError("sandbox_id must not be empty")
        if not self.status:
            raise ValueError("status must not be empty")
