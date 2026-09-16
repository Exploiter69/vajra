from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class IntegrityViolation:
    path: str
    rule: str
    detail: str


@dataclass(frozen=True)
class IntegrityReport:
    baseline_revision: str
    violations: tuple[IntegrityViolation, ...]
    protected_digest: str

    @property
    def valid(self) -> bool:
        return not self.violations


class TestIntegrityAuditor:
    """Audit protected verification inputs against a captured baseline."""

    FORBIDDEN_PATTERNS = (
        ("pytest.skip", "test_skip"),
        ("pytest.xfail", "test_xfail"),
        ("@pytest.mark.skip", "test_skip_marker"),
        ("@pytest.mark.xfail", "test_xfail_marker"),
        ("unittest.mock", "mock_dependency"),
        ("mock.patch", "mock_dependency"),
        ("monkeypatch", "test_monkeypatch"),
    )

    def snapshot(self, root: Path, protected_paths: Iterable[str], *, revision: str) -> dict[str, str]:
        del revision
        result: dict[str, str] = {}
        for relative in sorted(set(protected_paths)):
            path = self._safe_path(root, relative)
            if not path.is_file():
                raise ValueError(f"protected path is not a file: {relative}")
            result[relative] = self._file_digest(path)
        return result

    def audit(
        self,
        root: Path,
        protected_paths: Iterable[str],
        baseline: dict[str, str],
        *,
        baseline_revision: str,
    ) -> IntegrityReport:
        violations: list[IntegrityViolation] = []
        current: dict[str, str] = {}
        for relative in sorted(set(protected_paths) | set(baseline)):
            path = self._safe_path(root, relative)
            if path.is_file():
                current[relative] = self._file_digest(path)
        for relative in sorted(set(baseline) | set(current)):
            if relative not in current:
                violations.append(IntegrityViolation(relative, "protected_file_missing", "protected verification input was deleted"))
            elif relative not in baseline:
                violations.append(IntegrityViolation(relative, "protected_file_added", "unapproved verification input was added"))
            elif baseline[relative] != current[relative]:
                violations.append(IntegrityViolation(relative, "protected_file_modified", "protected verification input changed"))

        for relative in sorted(current):
            path = self._safe_path(root, relative)
            if path.suffix == ".py":
                text = path.read_text(encoding="utf-8")
                for needle, rule in self.FORBIDDEN_PATTERNS:
                    if needle in text:
                        violations.append(IntegrityViolation(relative, rule, f"verification input contains forbidden pattern: {needle}"))

        digest_payload = "\n".join(f"{key}:{value}" for key, value in sorted(current.items()))
        protected_digest = hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()
        return IntegrityReport(baseline_revision, tuple(violations), protected_digest)

    @staticmethod
    def _safe_path(root: Path, relative: str) -> Path:
        path = (root / relative).resolve()
        root_resolved = root.resolve()
        if path != root_resolved and root_resolved not in path.parents:
            raise ValueError(f"unsafe protected path: {relative}")
        return path

    @staticmethod
    def _file_digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
