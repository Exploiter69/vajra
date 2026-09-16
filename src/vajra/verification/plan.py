from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence

from vajra.control.contracts import AcceptanceCriteria, stable_digest


class CriterionKind(str, Enum):
    COMMAND_EXIT = "COMMAND_EXIT"
    FILE_EXISTS = "FILE_EXISTS"
    FILE_CONTAINS = "FILE_CONTAINS"
    GIT_CLEAN = "GIT_CLEAN"


@dataclass(frozen=True)
class CompiledCheck:
    check_id: str
    predicate_id: str
    kind: CriterionKind
    parameters: tuple[tuple[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "predicate_id": self.predicate_id,
            "kind": self.kind.value,
            "parameters": dict(self.parameters),
        }


@dataclass(frozen=True)
class FrozenVerificationPlan:
    plan_id: str
    version: str
    objective_digest: str
    checks: tuple[CompiledCheck, ...]
    created_at: datetime
    frozen_at: datetime
    integrity_digest: str


class AcceptanceCriteriaCompiler:
    """Compile declarative acceptance criteria into an immutable check plan.

    Natural-language text is not silently interpreted as executable authority.
    Callers must provide explicit, machine-checkable criterion mappings.
    """

    VERSION = "acceptance-compiler-v1"

    def compile(
        self,
        objective: str,
        criteria: AcceptanceCriteria,
        specifications: Sequence[Mapping[str, Any]],
    ) -> FrozenVerificationPlan:
        if not objective:
            raise ValueError("objective must not be empty")
        if not criteria.frozen:
            raise ValueError("acceptance criteria must be frozen before compilation")
        if stable_digest(objective) != criteria.objective_digest:
            raise ValueError("acceptance criteria objective digest mismatch")
        if len(specifications) != len(criteria.predicates):
            raise ValueError("each acceptance predicate requires one executable specification")

        predicates = {predicate.predicate_id: predicate for predicate in criteria.predicates}
        checks: list[CompiledCheck] = []
        for index, specification in enumerate(specifications):
            predicate_id = str(specification.get("predicate_id", ""))
            predicate = predicates.get(predicate_id)
            if predicate is None:
                raise ValueError(f"unknown predicate_id: {predicate_id}")
            kind_raw = str(specification.get("kind", ""))
            try:
                kind = CriterionKind(kind_raw)
            except ValueError as exc:
                raise ValueError(f"unsupported criterion kind: {kind_raw}") from exc
            parameters = self._validate_parameters(kind, specification)
            checks.append(
                CompiledCheck(
                    check_id=f"{criteria.criteria_id}:{index + 1}",
                    predicate_id=predicate.predicate_id,
                    kind=kind,
                    parameters=tuple(sorted(parameters.items())),
                )
            )

        created = criteria.created_at
        frozen = criteria.frozen_at
        assert frozen is not None
        payload = {
            "plan_id": criteria.criteria_id,
            "version": self.VERSION,
            "objective_digest": criteria.objective_digest,
            "checks": [check.as_dict() for check in checks],
            "created_at": created.astimezone(timezone.utc).isoformat(),
            "frozen_at": frozen.astimezone(timezone.utc).isoformat(),
        }
        return FrozenVerificationPlan(
            plan_id=criteria.criteria_id,
            version=self.VERSION,
            objective_digest=criteria.objective_digest,
            checks=tuple(checks),
            created_at=created,
            frozen_at=frozen,
            integrity_digest=stable_digest(payload),
        )

    @staticmethod
    def _validate_parameters(kind: CriterionKind, specification: Mapping[str, Any]) -> dict[str, Any]:
        if kind is CriterionKind.COMMAND_EXIT:
            command = specification.get("command")
            expected = specification.get("expected_exit_code")
            if not isinstance(command, (list, tuple)) or not command or not all(isinstance(x, str) and x for x in command):
                raise ValueError("COMMAND_EXIT requires a non-empty command sequence")
            if not isinstance(expected, int):
                raise ValueError("COMMAND_EXIT requires integer expected_exit_code")
            return {"command": tuple(command), "expected_exit_code": expected}
        if kind is CriterionKind.GIT_CLEAN:
            return {}
        path = specification.get("path")
        if not isinstance(path, str) or not path or path.startswith("/") or ".." in path.split("/"):
            raise ValueError("file criteria require a safe relative path")
        if kind is CriterionKind.FILE_EXISTS:
            return {"path": path}
        if kind is CriterionKind.FILE_CONTAINS:
            needle = specification.get("needle")
            if not isinstance(needle, str) or not needle:
                raise ValueError("FILE_CONTAINS requires a non-empty needle")
            return {"path": path, "needle": needle}
        raise ValueError(f"unsupported criterion kind: {kind.value}")
