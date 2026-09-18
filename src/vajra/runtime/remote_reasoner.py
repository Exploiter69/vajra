from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from vajra.autonomy.contracts import EngineeringPlan, PlannedIntent
from vajra.context.contracts import ContextBundle
from vajra.routing.contracts import BudgetEnvelope, ModelRequest, ModelResult


class ModelProposalError(RuntimeError):
    """Remote model output is not safe to consume."""


@dataclass
class GatewayReasoner:
    gateway: object
    model_identity: str
    max_output_tokens: int = 1200

    def orient(self, context: ContextBundle) -> str:
        result = self._invoke(
            context,
            "orientation",
            "Return JSON only with an orientation string. You are VAJRA's proposal-only reasoning component, not its authority. Objective: "
            + context.query
            + ". Relevant files: " + repr(list(context.relevant_files))
            + ". Acceptance: " + repr(list(context.acceptance_criteria)),
            {"type": "object", "required": ["orientation"]},
        )
        value = result.structured_output.get("orientation")
        if not isinstance(value, str) or not value.strip():
            raise ModelProposalError("model returned no orientation")
        return value.strip()

    def plan(self, context: ContextBundle, orientation: str) -> EngineeringPlan:
        result = self._invoke(context, "plan", self._plan_prompt(context, orientation),
                              {"type": "object", "required": ["plan_id", "strategy_id", "intents"]})
        return self._parse_plan(result, context)

    def replan(self, context: ContextBundle, previous_plan: EngineeringPlan, failure_reason: str) -> EngineeringPlan:
        result = self._invoke(
            context, "replan",
            self._plan_prompt(context, "Previous plan failed: " + failure_reason + ". Previous plan: " + repr(previous_plan)),
            {"type": "object", "required": ["plan_id", "strategy_id", "intents"]},
        )
        return self._parse_plan(result, context)

    def _invoke(self, context: ContextBundle, phase: str, task: str, schema: dict) -> ModelResult:
        request = ModelRequest(
            request_id=str(uuid4()), run_id=context.run_id, step_id="model-" + phase,
            attempt_id=str(uuid4()), task=task,
            context={"revision": context.revision, "context_digest": context.digest},
            output_schema=schema,
            budget=BudgetEnvelope(max_model_calls=1, max_worker_runtime_seconds=300,
                                  max_output_size=self.max_output_tokens * 4, max_cost_units=0),
            deadline=(datetime.now(timezone.utc) + timedelta(seconds=300)).replace(microsecond=0).isoformat(),
            model=self.model_identity, strategy_id="qwen-" + phase,
        )
        result = self.gateway.invoke(request, self.model_identity)
        if result.status != "SUCCEEDED":
            raise ModelProposalError("; ".join(result.errors) or "remote model failed")
        return result

    def _plan_prompt(self, context: ContextBundle, orientation: str) -> str:
        return (
            "You are VAJRA's proposal-only reasoning component. The controller, policy engine, "
            "execution broker and independent verifier are authoritative. Do not claim execution or verification.\n"
            "OBJECTIVE: " + context.query + "\nORIENTATION: " + orientation
            + "\nRELEVANT FILES: " + repr(list(context.relevant_files))
            + "\nACCEPTANCE: " + repr(list(context.acceptance_criteria))
            + "\nProduce the smallest plan satisfying the objective. Allowed operation: WRITE_FILE only. "
            "Allowed paths: calculator.py and test_calculator.py only. Each intent must contain COMPLETE file content. "
            "No shell commands, absolute paths, git operations, or extra fields. Return JSON only with plan_id, strategy_id, "
            "and intents containing intent_id, operation, path, content, reason."
        )

    def _parse_plan(self, result: ModelResult, context: ContextBundle) -> EngineeringPlan:
        payload = result.structured_output
        raw = payload.get("response") if isinstance(payload, dict) else None
        if isinstance(raw, str):
            text = raw.strip()
            lines = text.splitlines()
            if lines and lines[0].lstrip().startswith(chr(96)):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith(chr(96)):
                lines = lines[:-1]
            payload = json.loads("\n".join(lines).strip())
        if not isinstance(payload, dict):
            raise ModelProposalError("model plan is not a JSON object")

        intents = []
        for item in payload.get("intents", []):
            if not isinstance(item, dict):
                raise ModelProposalError("plan intent is not an object")
            operation, path, body = item.get("operation"), item.get("path"), item.get("content")
            if operation != "WRITE_FILE":
                raise ModelProposalError("model proposed a forbidden operation")
            if path not in {"calculator.py", "test_calculator.py"}:
                raise ModelProposalError("model proposed forbidden path: " + repr(path))
            if not isinstance(body, str) or not body:
                raise ModelProposalError("model intent has no file content")
            intents.append(PlannedIntent(
                intent_id=str(item.get("intent_id") or uuid4()), operation=operation,
                parameters={"path": path, "content": body},
                reason=str(item.get("reason") or "model-proposed bounded file change"),
                strategy_id=str(payload.get("strategy_id") or "qwen-run-3"),
            ))
        if not intents:
            raise ModelProposalError("model returned an empty plan")
        return EngineeringPlan(
            plan_id=str(payload.get("plan_id") or uuid4()), context_digest=context.digest,
            intents=tuple(intents), strategy_id=str(payload.get("strategy_id") or "qwen-run-3"),
        )
