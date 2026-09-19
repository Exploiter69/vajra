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
    single_call_plan: bool = False
    _cached_plan: EngineeringPlan | None = None
    _cached_plan_context_digest: str | None = None

    def orient(self, context: ContextBundle) -> str:
        if self.single_call_plan:
            result = self._invoke(
                context,
                "orientation-plan",
                self._combined_prompt(context),
                {"type": "object", "required": ["orientation", "plan_id", "strategy_id", "intents"]},
            )
            payload = result.structured_output
            raw = payload.get("response") if isinstance(payload, dict) else None
            if isinstance(raw, str):
                payload = self._parse_json_response(raw)
                result = ModelResult(
                    status=result.status,
                    structured_output=payload,
                    usage=result.usage,
                    model_identity=result.model_identity,
                    errors=result.errors,
                )
            value = payload.get("orientation") if isinstance(payload, dict) else None
            if not isinstance(value, str) or not value.strip():
                raise ModelProposalError("model returned no orientation")
            self._cached_plan = self._parse_plan(result, context)
            self._cached_plan_context_digest = context.digest
            return value.strip()

        result = self._invoke(
            context,
            "orientation",
            "Return JSON only with an orientation string. You are VAJRA's proposal-only reasoning component, not its authority. Objective: "
            + context.query
            + ". Relevant files: " + repr(list(context.relevant_files))
            + ". Acceptance: " + repr(list(context.acceptance_criteria)),
            {"type": "object", "required": ["orientation"]},
        )
        payload = result.structured_output
        value = payload.get("orientation") if isinstance(payload, dict) else None
        if not isinstance(value, str) or not value.strip():
            raw = payload.get("response") if isinstance(payload, dict) else None
            if isinstance(raw, str):
                try:
                    parsed = self._parse_json_response(raw)
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ModelProposalError("model orientation response is not valid JSON") from exc
                value = parsed.get("orientation") if isinstance(parsed, dict) else None
        if not isinstance(value, str) or not value.strip():
            raise ModelProposalError("model returned no orientation")
        return value.strip()

    def plan(self, context: ContextBundle, orientation: str) -> EngineeringPlan:
        if self.single_call_plan and self._cached_plan_context_digest == context.digest and self._cached_plan is not None:
            plan = self._cached_plan
            self._cached_plan = None
            self._cached_plan_context_digest = None
            return plan
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
            budget=BudgetEnvelope(max_model_calls=1, max_worker_runtime_seconds=900,
                                  max_output_size=self.max_output_tokens * 4, max_cost_units=0),
            deadline=(datetime.now(timezone.utc) + timedelta(seconds=900)).replace(microsecond=0).isoformat(),
            model=self.model_identity, strategy_id="qwen-" + phase,
        )
        result = self.gateway.invoke(request, self.model_identity)
        if result.status != "SUCCEEDED":
            raise ModelProposalError("; ".join(result.errors) or "remote model failed")
        return result

    @staticmethod
    def _parse_json_response(raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```") and text.endswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]).strip()
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("model response is not a JSON object")
        return payload

    def _combined_prompt(self, context: ContextBundle) -> str:
        return (
            "You are VAJRA's proposal-only reasoning component. The controller, policy engine, "
            "execution broker and independent verifier are authoritative. Do not claim execution or verification. "
            "Produce ONE JSON object containing both an orientation string and a complete bounded plan.\n"
            "OBJECTIVE: " + context.query
            + "\nRELEVANT FILES: " + repr(list(context.relevant_files))
            + "\nACCEPTANCE: " + repr(list(context.acceptance_criteria))
            + "\nThe plan must use WRITE_FILE only, paths calculator.py and test_calculator.py only, "
            "and each intent must contain COMPLETE file content. No shell commands, absolute paths, git operations, "
            "or extra fields. Return JSON only with orientation, plan_id, strategy_id, and intents containing "
            "intent_id, operation, path, content, reason."
        )

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
            payload = self._parse_json_response("\n".join(lines).strip())
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
