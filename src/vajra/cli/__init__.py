"""VAJRA command-line interface."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name in {"build_parser", "main"}:
        from vajra.cli.main import build_parser, main

        return {
            "build_parser": build_parser,
            "main": main,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["build_parser", "main"]
