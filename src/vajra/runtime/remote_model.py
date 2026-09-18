from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from vajra.routing.contracts import ModelIdentity, ModelRequest, ModelResult, ModelUsage
from vajra.runtime.http_worker_transport import HTTPWorkerTransport
from vajra.runtime.worker_protocol import WorkerJob


@dataclass(frozen=True)
class RemoteWorkerModelAdapter:
    """ModelGateway adapter for an existing VAJRA HTTP worker."""

    endpoint: str
    identity: ModelIdentity
    timeout_seconds: int = 300

    def invoke(self, request: ModelRequest) -> ModelResult:
        started = monotonic()
        job = WorkerJob(
            run_id=request.run_id,
            step_id=request.step_id,
            attempt_id=request.attempt_id,
            repository_revision=str(request.context.get("revision", "unknown")),
            workspace_contract={"mode": "proposal-only", "authority": "vajra-control-plane"},
            context_bundle={"prompt": request.task, "request_id": request.request_id},
            allowed_capabilities=(),
            budget={
                "max_output_tokens": int(request.budget.max_output_size // 4),
                "timeout_seconds": self.timeout_seconds,
            },
            deadline=request.deadline,
            expected_output_schema=request.output_schema,
            correlation_id=request.request_id,
        )
        result = HTTPWorkerTransport(
            self.endpoint, timeout_seconds=self.timeout_seconds
        ).execute(job)
        usage = ModelUsage(
            model_calls=1,
            input_tokens=int(result.usage.get("prompt_eval_count") or 0),
            output_tokens=int(result.usage.get("eval_count") or 0),
            runtime_seconds=monotonic() - started,
            cost_units=0,
        )
        return ModelResult(
            status="SUCCEEDED" if result.status == "completed" else "FAILED",
            structured_output=result.structured_result or {},
            usage=usage,
            model_identity=self.identity,
            errors=result.errors,
        )


def build_remote_gateway(endpoint: str, identity: ModelIdentity):
    from vajra.routing.gateway import ModelGateway, ModelRegistry

    return ModelGateway(ModelRegistry((RemoteWorkerModelAdapter(endpoint, identity),)))


@dataclass(frozen=True)
class TransportWorkerModelAdapter:
    """ModelGateway adapter for any synchronous WorkerTransport."""

    transport: object
    identity: ModelIdentity
    timeout_seconds: int = 300

    def invoke(self, request: ModelRequest) -> ModelResult:
        started = monotonic()
        job = WorkerJob(
            run_id=request.run_id,
            step_id=request.step_id,
            attempt_id=request.attempt_id,
            repository_revision=str(request.context.get("revision", "unknown")),
            workspace_contract={"mode": "proposal-only", "authority": "vajra-control-plane"},
            context_bundle={"prompt": request.task, "request_id": request.request_id},
            allowed_capabilities=(),
            budget={
                "max_output_tokens": int(request.budget.max_output_size // 4),
                "timeout_seconds": self.timeout_seconds,
            },
            deadline=request.deadline,
            expected_output_schema=request.output_schema,
            correlation_id=request.request_id,
        )
        result = self.transport.execute(job)
        usage = ModelUsage(
            model_calls=1,
            input_tokens=int(result.usage.get("prompt_eval_count") or 0),
            output_tokens=int(result.usage.get("eval_count") or 0),
            runtime_seconds=monotonic() - started,
            cost_units=0,
        )
        return ModelResult(
            status="SUCCEEDED" if result.status == "completed" else "FAILED",
            structured_output=result.structured_result or {},
            usage=usage,
            model_identity=self.identity,
            errors=result.errors,
        )


def build_kaggle_batch_gateway(
    kernel_template, kernel_ref: str, *, executable: str = "kaggle",
    timeout_seconds: int = 900, poll_interval_seconds: float = 5.0,
):
    from vajra.routing.gateway import ModelGateway, ModelRegistry

    identity = ModelIdentity("kaggle", "qwen2.5-coder:32b", "ollama", "kaggle-batch")
    transport = KaggleBatchWorkerTransport(
        kernel_template=kernel_template,
        kernel_ref=kernel_ref,
        executable=executable,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    return ModelGateway(ModelRegistry((TransportWorkerModelAdapter(transport, identity),)))
