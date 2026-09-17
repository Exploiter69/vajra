from __future__ import annotations

import unittest

from vajra.routing import (
    BudgetEnvelope,
    CallableModelAdapter,
    CapabilityRouter,
    Complexity,
    ModelGateway,
    ModelGatewayError,
    ModelIdentity,
    ModelRegistry,
    ModelRequest,
    ModelResult,
    ModelUsage,
    RecoveryAction,
    RoutingRecovery,
    TaskProfile,
    WorkerCapabilities,
    WorkerDescriptor,
    WorkerRegistry,
)


def identity(provider: str, model: str, version: str) -> ModelIdentity:
    return ModelIdentity(provider, model, version, "test")


def worker(worker_id: str, model: str, tasks: frozenset[str], *, reliability: float = 1.0, cost: int = 0) -> WorkerDescriptor:
    return WorkerDescriptor(
        worker_id,
        WorkerCapabilities(
            accelerator="test" if worker_id != "cpu" else None,
            vram_gib=16 if worker_id != "cpu" else 0,
            system_ram_gib=32,
            model=model,
            model_version="1",
            context_limit=32768,
            supported_tasks=tasks,
            sandbox_type="isolated",
            network_policy="none",
        ),
        reliability=reliability,
        latency_ms=10,
        cost_units=cost,
        metadata={"provider": "local", "adapter": "test"},
    )


class Phase12RoutingTests(unittest.TestCase):
    def test_model_identity_is_canonical_and_versioned(self) -> None:
        self.assertEqual(identity("ollama", "qwen", "7b").canonical, "ollama:qwen@7b")

    def test_gateway_preserves_identity_and_usage(self) -> None:
        ident = identity("local", "small", "1")
        result = ModelResult("SUCCEEDED", {"ok": True}, usage=ModelUsage(1, 10, 5, 0.2), model_identity=ident)
        registry = ModelRegistry((CallableModelAdapter(ident, lambda _: result),))
        request = ModelRequest("r1", "run", "step", "attempt", "extract", deadline="2030-01-01T00:00:00Z")
        got = ModelGateway(registry).invoke(request, ident.canonical)
        self.assertEqual(got.model_identity, ident)
        self.assertEqual(got.usage.output_tokens, 5)

    def test_gateway_turns_adapter_failure_into_data(self) -> None:
        ident = identity("local", "broken", "1")
        registry = ModelRegistry((CallableModelAdapter(ident, lambda _: (_ for _ in ()).throw(RuntimeError("boom"))),))
        request = ModelRequest("r2", "run", "step", "attempt", "extract", deadline="2030-01-01T00:00:00Z")
        result = ModelGateway(registry).invoke(request, ident.canonical)
        self.assertEqual(result.status, "FAILED")
        self.assertIn("boom", result.errors[0])

    def test_gateway_rejects_unknown_model(self) -> None:
        ident = identity("local", "small", "1")
        gateway = ModelGateway(ModelRegistry((CallableModelAdapter(ident, lambda _: ModelResult("SUCCEEDED", model_identity=ident)),)))
        request = ModelRequest("r3", "run", "step", "attempt", "extract", deadline="2030-01-01T00:00:00Z")
        with self.assertRaises(ModelGatewayError):
            gateway.invoke(request, "missing:model@1")

    def test_complexity_classification(self) -> None:
        router = CapabilityRouter(WorkerRegistry((worker("w", "m", frozenset({"code"})),)))
        self.assertEqual(router.classify("simple extraction"), Complexity.SIMPLE)
        self.assertEqual(router.classify("mechanical edit"), Complexity.MECHANICAL)
        self.assertEqual(router.classify("implement code"), Complexity.COMPLEX)
        self.assertEqual(router.classify("debug race condition"), Complexity.DIFFICULT)

    def test_capability_fit_beats_ineligible_worker(self) -> None:
        registry = WorkerRegistry((worker("small", "m1", frozenset({"extract"})), worker("code", "m2", frozenset({"code"}))))
        decision = CapabilityRouter(registry).select_for_request("req", TaskProfile("code", Complexity.COMPLEX))
        self.assertEqual(decision.worker_id, "code")
        self.assertEqual(decision.evidence.selected_worker, "code")
        self.assertEqual(decision.evidence.request_id, "req")

    def test_deterministic_selection_uses_stable_tiebreaker(self) -> None:
        registry = WorkerRegistry((worker("b", "m", frozenset({"x"})), worker("a", "m", frozenset({"x"}))))
        router = CapabilityRouter(registry)
        profile = TaskProfile("x", Complexity.SIMPLE)
        self.assertEqual(router.select(profile).worker_id, "a")
        self.assertEqual(router.select(profile).worker_id, "a")

    def test_budget_is_enforced(self) -> None:
        registry = WorkerRegistry((worker("paid", "m", frozenset({"x"}), cost=1), worker("free", "m", frozenset({"x"}), cost=0)))
        decision = CapabilityRouter(registry).select(TaskProfile("x", Complexity.SIMPLE, max_cost_units=0))
        self.assertEqual(decision.worker_id, "free")

    def test_no_capability_match_fails_closed(self) -> None:
        router = CapabilityRouter(WorkerRegistry((worker("w", "m", frozenset({"x"})),)))
        with self.assertRaises(Exception):
            router.select(TaskProfile("code", Complexity.COMPLEX, required_capabilities=frozenset({"gpu"})))

    def test_routing_evidence_names_all_candidates(self) -> None:
        registry = WorkerRegistry((worker("b", "m", frozenset({"x"})), worker("a", "m", frozenset({"x"}))))
        decision = CapabilityRouter(registry).select_for_request("req", TaskProfile("x", Complexity.SIMPLE))
        self.assertEqual(decision.evidence.candidates, ("a", "b"))
        self.assertEqual(decision.model.version, "1")

    def test_different_model_recovery(self) -> None:
        registry = WorkerRegistry((worker("a", "m1", frozenset({"x"})), worker("b", "m2", frozenset({"x"}))))
        recovery = RoutingRecovery(CapabilityRouter(registry))
        plan = recovery.next(TaskProfile("x", Complexity.COMPLEX), request_id="r", attempt_index=1, same_model_failures=1, tried_models=frozenset({"local:m1@1"}), tried_workers=frozenset({"a"}), strategy_changed=True)
        self.assertEqual(plan.action, RecoveryAction.DIFFERENT_MODEL)

    def test_different_worker_recovery_when_model_is_shared(self) -> None:
        registry = WorkerRegistry((worker("a", "m", frozenset({"x"})), worker("b", "m", frozenset({"x"}))))
        recovery = RoutingRecovery(CapabilityRouter(registry))
        plan = recovery.next(TaskProfile("x", Complexity.SIMPLE), request_id="r", attempt_index=1, same_model_failures=1, tried_workers=frozenset({"a"}), strategy_changed=True)
        self.assertEqual(plan.action, RecoveryAction.DIFFERENT_WORKER)

    def test_same_model_retry_is_bounded(self) -> None:
        router = CapabilityRouter(WorkerRegistry((worker("a", "m", frozenset({"x"})),)))
        recovery = RoutingRecovery(router, max_same_model_retries=1)
        profile = TaskProfile("x", Complexity.SIMPLE)
        self.assertEqual(recovery.next(profile, request_id="r", attempt_index=0, same_model_failures=0).action, RecoveryAction.SAME_MODEL_RETRY)
        self.assertEqual(recovery.next(profile, request_id="r", attempt_index=1, same_model_failures=1).action, RecoveryAction.DIFFERENT_STRATEGY)

    def test_strategy_change_precedes_resource_switch(self) -> None:
        router = CapabilityRouter(WorkerRegistry((worker("a", "m", frozenset({"x"})),)))
        plan = RoutingRecovery(router).next(TaskProfile("x", Complexity.SIMPLE), request_id="r", attempt_index=1, same_model_failures=1)
        self.assertEqual(plan.action, RecoveryAction.DIFFERENT_STRATEGY)
        self.assertTrue(plan.profile.strategy_id.endswith(":alternate"))

    def test_exhausted_routing_escalates_to_human(self) -> None:
        router = CapabilityRouter(WorkerRegistry((worker("a", "m", frozenset({"x"})),)))
        profile = TaskProfile("x", Complexity.SIMPLE)
        plan = RoutingRecovery(router).next(profile, request_id="r", attempt_index=2, same_model_failures=1, tried_models=frozenset({"local:m@1"}), tried_workers=frozenset({"a"}), strategy_changed=True)
        self.assertEqual(plan.action, RecoveryAction.HUMAN)

    def test_budget_envelope_rejects_negative_values(self) -> None:
        with self.assertRaises(ValueError):
            BudgetEnvelope(max_model_calls=-1)


if __name__ == "__main__":
    unittest.main()
