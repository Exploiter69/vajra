from __future__ import annotations

import ast
import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .contracts import IndexFile, RepositoryIndex, stable_digest


DEFAULT_IGNORED_DIRS = frozenset({
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".venv", "venv", "node_modules", "dist", "build", ".tox",
})

LANGUAGES = {
    ".py": "python", ".pyi": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".go": "go", ".rs": "rust",
    ".java": "java", ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
    ".md": "markdown", ".mdx": "markdown", ".toml": "toml", ".yaml": "yaml",
    ".yml": "yaml", ".json": "json", ".txt": "text", ".sh": "shell",
}

_IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


@dataclass(frozen=True)
class IndexConfig:
    max_file_bytes: int = 1_048_576
    max_history: int = 32
    ignored_dirs: frozenset[str] = DEFAULT_IGNORED_DIRS


class RepositoryIndexer:
    """Builds a deterministic, dependency-light repository index."""

    def __init__(self, config: IndexConfig | None = None) -> None:
        self.config = config or IndexConfig()

    @staticmethod
    def _git(root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    def build(self, root: str | Path, revision: str | None = None) -> RepositoryIndex:
        path = Path(root).expanduser().resolve()
        if not path.is_dir():
            raise ValueError(f"repository does not exist: {path}")
        actual_revision = revision or self._git(path, "rev-parse", "HEAD") or "WORKTREE"
        files: list[IndexFile] = []
        for current, dirs, names in os.walk(path):
            dirs[:] = sorted(d for d in dirs if d not in self.config.ignored_dirs)
            for name in sorted(names):
                candidate = Path(current) / name
                relative = candidate.relative_to(path).as_posix()
                try:
                    stat = candidate.lstat()
                except OSError:
                    continue
                if not candidate.is_file() or stat.st_size > self.config.max_file_bytes:
                    continue
                try:
                    raw = candidate.read_bytes()
                except OSError:
                    continue
                if b"\x00" in raw:
                    continue
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                digest = hashlib.sha256(raw).hexdigest()
                language = LANGUAGES.get(candidate.suffix.lower(), "text")
                symbols, references, dependencies = self._extract(text, language)
                files.append(IndexFile(
                    path=relative, digest=digest, size=len(raw), language=language,
                    symbols=tuple(sorted(symbols)), references=tuple(sorted(references)),
                    dependencies=tuple(sorted(dependencies)),
                ))
        files.sort(key=lambda item: item.path)
        fs_digest = stable_digest([(f.path, f.digest, f.size) for f in files])
        history = tuple(self._git(path, "log", f"-{self.config.max_history}", "--format=%H %s").splitlines())
        payload = {"root": str(path), "revision": actual_revision, "filesystem_digest": fs_digest, "files": files, "history": history}
        return RepositoryIndex(
            root=str(path), revision=actual_revision, filesystem_digest=fs_digest,
            files=tuple(files), history=history, digest=stable_digest(payload),
        )

    @staticmethod
    def _extract(text: str, language: str) -> tuple[set[str], set[str], set[str]]:
        symbols: set[str] = set()
        references: set[str] = set()
        dependencies: set[str] = set()
        if language == "python":
            try:
                tree = ast.parse(text)
            except SyntaxError:
                tree = None
            if tree is not None:
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        symbols.add(node.name)
                    elif isinstance(node, ast.Import):
                        for item in node.names:
                            dependencies.add(item.name)
                            references.add(item.name.split(".")[-1])
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            dependencies.add(node.module)
                        for item in node.names:
                            references.add(item.name)
                return symbols, references, dependencies
        for match in re.finditer(r"(?:function|class|def|func|fn)\s+([A-Za-z_][A-Za-z0-9_]*)", text):
            symbols.add(match.group(1))
        references.update(_IDENTIFIER.findall(text))
        return symbols, references, dependencies


__all__ = ["IndexConfig", "RepositoryIndexer"]
