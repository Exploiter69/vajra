from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Mapping, Sequence

from .contracts import HardeningViolation


_SECRET_NAME = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|PRIVATE_KEY|API_KEY|ACCESS_KEY|CREDENTIAL)", re.I)
_INJECTION = re.compile(
    r"(ignore|disregard|override)\s+(all\s+)?(previous|prior|above)\s+instructions|"
    r"(system|developer)\s+message\s*[:=]|"
    r"(disable|bypass)\s+(safety|security|policy)",
    re.I,
)
_SENSITIVE_PATH = re.compile(
    r"(^|/)(\.env(?:\..*)?|id_(rsa|dsa|ecdsa|ed25519)|credentials?\.json|"
    r"\.aws/|\.ssh/|.*\.pem)$",
    re.I,
)
_LIFECYCLE = {"preinstall", "install", "postinstall", "prepare"}


class SecurityPolicy:
    """Fail-closed validation of hostile repository and execution boundaries."""

    def __init__(
        self,
        *,
        workspace_root: str | Path | None = None,
        allow_network: bool = False,
        allow_symlinks: bool = False,
        allow_submodules: bool = False,
        allow_git_hooks: bool = False,
        allow_package_scripts: bool = False,
        allowed_environment: Sequence[str] = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR"),
    ) -> None:
        self.workspace_root = Path(workspace_root).expanduser().resolve() if workspace_root else None
        self.allow_network = allow_network
        self.allow_symlinks = allow_symlinks
        self.allow_submodules = allow_submodules
        self.allow_git_hooks = allow_git_hooks
        self.allow_package_scripts = allow_package_scripts
        self.allowed_environment = frozenset(allowed_environment)

    def validate_workspace(self, path: str | Path) -> Path:
        raw = Path(path).expanduser()
        resolved = raw.resolve(strict=False)
        if self.workspace_root is not None:
            try:
                resolved.relative_to(self.workspace_root)
            except ValueError as exc:
                raise HardeningViolation("workspace escapes configured root") from exc
        current = raw
        parts = []
        while True:
            parts.append(current)
            if current == current.parent:
                break
            current = current.parent
        for candidate in reversed(parts):
            if candidate.exists() and candidate.is_symlink() and not self.allow_symlinks:
                raise HardeningViolation(f"symlink path component is forbidden: {candidate}")
        if not resolved.is_dir():
            raise HardeningViolation(f"workspace is not a directory: {resolved}")
        return resolved

    def validate_environment(self, env: Mapping[str, str]) -> dict[str, str]:
        sanitized: dict[str, str] = {}
        for name, value in env.items():
            if name not in self.allowed_environment or _SECRET_NAME.search(name):
                raise HardeningViolation(f"environment variable is not permitted: {name}")
            if not isinstance(value, str):
                raise HardeningViolation(f"environment value must be text: {name}")
            sanitized[name] = value
        return sanitized

    def validate_command(self, command: Sequence[str], *, network_enabled: bool) -> None:
        if not command or not all(isinstance(x, str) and x for x in command):
            raise HardeningViolation("command must be a non-empty sequence of strings")
        if network_enabled and not self.allow_network:
            raise HardeningViolation("network access is not permitted by security policy")
        lowered = " ".join(command).lower()
        if any(token in lowered for token in ("/.ssh/", "/.aws/", ".env", "id_rsa", "credentials.json", ".pem")):
            raise HardeningViolation("command references a sensitive credential path")

    def scan_repository(self, root: str | Path) -> tuple[str, ...]:
        root_path = self.validate_workspace(root)
        findings: list[str] = []
        for current, dirs, files in os.walk(root_path, followlinks=False):
            dirs[:] = sorted(dirs)
            for name in sorted(files):
                path = Path(current) / name
                rel = path.relative_to(root_path).as_posix()
                if path.is_symlink() and not self.allow_symlinks:
                    findings.append(f"SYMLINK:{rel}")
                if rel == ".gitmodules" and not self.allow_submodules:
                    findings.append("SUBMODULE:.gitmodules")
                if rel == ".git/hooks" or rel.startswith(".git/hooks/"):
                    if not self.allow_git_hooks:
                        findings.append(f"GIT_HOOK:{rel}")
                if _SENSITIVE_PATH.search(rel):
                    findings.append(f"CREDENTIAL_PATH:{rel}")
                if path.name == "package.json" and not self.allow_package_scripts:
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                        scripts = data.get("scripts") or {}
                        bad = sorted(_LIFECYCLE.intersection(scripts))
                        if bad:
                            findings.append(f"PACKAGE_LIFECYCLE:{rel}:{','.join(bad)}")
                    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                        findings.append(f"INVALID_PACKAGE_MANIFEST:{rel}")
        return tuple(findings)

    @staticmethod
    def inspect_untrusted_text(text: str) -> tuple[str, ...]:
        if not isinstance(text, str):
            raise HardeningViolation("untrusted text must be a string")
        return tuple(match.group(0) for match in _INJECTION.finditer(text))

    def validate_untrusted_text(self, text: str) -> None:
        findings = self.inspect_untrusted_text(text)
        if findings:
            raise HardeningViolation("prompt-injection indicators detected")


__all__ = ["SecurityPolicy"]
