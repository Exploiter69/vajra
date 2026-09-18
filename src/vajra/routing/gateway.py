from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .contracts import ModelRequest, ModelResult
from vajra.hardening import ResourceGovernor


class ModelGatewayError(RuntimeError):
    """Raised when the model boundary cannot service a request."""


class ModelAdapter(Protocol):
    identity: object

    def invoke(self, request: ModelRequest) -> ModelResult: ...


@dataclass(frozen=True)
class CallableModelAdapter:
    """Dependency-free adapter for local models, test doubles, or future transports."""

    identity: object
    handler: Callable[[ModelRequest], ModelResult]

    def invoke(self, request: ModelRequest) -> ModelResult:
        result = self.handler(request)
        if result.model_identity is None:
            return ModelResult(
                status=result.status,
                structured_output=result.structured_output,
                raw_output_reference=result.raw_output_reference,
                usage=result.usage,
                model_identity=self.identity,  # type: ignore[arg-type]
                errors=result.errors,
                evidence=result.evidence,
            )
        return result


class ModelRegistry:
    def __init__(self, adapters: tuple[ModelAdapter, ...] = ()) -> None:
        self._adapters: dict[str, ModelAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: ModelAdapter) -> None:
        key = adapter.identity.canonical  # type: ignore[attr-defined]
        if key in self._adapters:
            raise ValueError(f"model already registered: {key}")
        self._adapters[key] = adapter

    def get(self, canonical_identity: str) -> ModelAdapter:
        try:
            return self._adapters[canonical_identity]
        except KeyError as exc:
            raise ModelGatewayError(f"unknown model: {canonical_identity}") from exc

    def identities(self) -> tuple[object, ...]:
        return tuple(self._adapters[k].identity for k in sorted(self._adapters))


class ModelGateway:
    """Stable model boundary. It routes only; policy and execution stay outside it."""

    VERSION = "model-gateway-v1"

    def __init__(self, registry: ModelRegistry, *, resource_governor: ResourceGovernor | None = None) -> None:
        self._registry = registry
        self._resource_governor = resource_governor

    def invoke(self, request: ModelRequest, model_identity: str | None = None) -> ModelResult:
        if model_identity is None:
            identities = self._registry.identities()
            if not identities:
                raise ModelGatewayError("no model adapters registered")
            identity = identities[0]
            model_identity = identity.canonical
        adapter = self._registry.get(model_identity)
        try:
            result = adapter.invoke(request)
        except Exception as exc:  # adapter failures become data at the boundary
            identity = adapter.identity
            from .contracts import ModelUsage

            return ModelResult(
                status="FAILED",
                model_identity=identity,
                usage=ModelUsage(model_calls=1),
                errors=(f"{type(exc).__name__}: {exc}",),
            )
        if result.model_identity is None:
            raise ModelGatewayError("adapter returned a result without model identity")
        if self._resource_governor is not None:
            decision = self._resource_governor.charge(
                model_calls=result.usage.model_calls,
                output_bytes=result.usage.output_tokens,
                worker_runtime_seconds=result.usage.runtime_seconds,
            )
            if not decision.allowed:
                raise ModelGatewayError(decision.reason)
        if result.model_identity.canonical != model_identity:
            raise ModelGatewayError("adapter result identity does not match selected model")
        return result
