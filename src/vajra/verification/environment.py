from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence


class VerificationEnvironmentError(ValueError):
    pass


@dataclass(frozen=True)
class VerificationEnvironment:
    """Controlled environment description for independent verification."""

    workspace: Path
    environment: tuple[tuple[str, str], ...] = ()
    timeout_seconds: int = 300
    network_enabled: bool = False
    worker_access: bool = False
    sandbox_id: str | None = None

    def __post_init__(self) -> None:
        if not self.workspace.is_absolute():
            raise VerificationEnvironmentError("workspace must be absolute")
        if self.timeout_seconds <= 0:
            raise VerificationEnvironmentError("timeout_seconds must be positive")
        if self.worker_access:
            raise VerificationEnvironmentError("verification environment must not grant worker access")
        if not self.network_enabled and self.sandbox_id is None:
            raise VerificationEnvironmentError("network-disabled verification requires an isolated sandbox")
        keys = [key for key, _ in self.environment]
        if len(keys) != len(set(keys)):
            raise VerificationEnvironmentError("verification environment contains duplicate variables")

    def env_dict(self) -> dict[str, str]:
        return dict(self.environment)


class VerificationExecutor(Protocol):
    def execute(self, command: Sequence[str], environment: VerificationEnvironment) -> tuple[int, str]:
        ...
