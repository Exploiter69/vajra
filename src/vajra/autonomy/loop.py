from __future__ import annotations

import hashlib
import subprocess
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from vajra.context import ContextBundle, ContextEngine
from vajra.control import AcceptanceCriteria, AcceptanceEvaluator, BoundedAutonomy, Controller, LimitAction
from vajra.control.contracts import DivergenceClass, PredicateResult
from vajra.domain import ArtifactRef, EngineeringRun, Event, RunState
from vajra.execution import ExecutionBroker
from vajra.execution.contracts import ExecutionRequest, ExecutionStatus
from vajra.policy import PolicyEvaluator
from vajra.recovery.progress import ProgressObservation
from vajra.runtime.event_store import EventStore, InMemoryEventStore
from vajra.runtime.state_store import InMemoryStateStore, StateStore
from vajra.runtime.worker_acceptance import WorkerExecutionIdentity, WorkerResultAcceptor
from vajra.runtime.worker_protocol import WorkerResult
from vajra.verification import IndependentVerifier, FrozenVerificationPlan, VerificationEnvironment

from .contracts import (
    EngineeringPlan,
    LoopPhase,
    LoopResult,
    NullLoopObserver,
    PlannedIntent,
    ProgressMeasurement,
    ReasoningProvider,
)


class AutonomousLoopError(RuntimeError):
    """Raised when the Phase 10 loop cannot continue safely."""


@dataclass(frozen=True)
class WorkspaceRuntime:
    workspace: Path
    workspace_id: str
    repository_id: str
    base_revision: str
    owner_token: str = ""


class _RunStateRecorder:
    """Narrow Phase 10 state/evidence writer behind the canonical StateStore."""

    def __init__(self, state_store: StateStore, event_store: EventStore) -> None:
        self._state = state_store
        self._events = event_store
        self._lock = RLock()

    def record_verification(self, run_id: str, results: tuple, evidence: tuple) -> None:
        with self._lock:
            run = self._state.get_run(run_id)
            previous = deepcopy(run)
            run.verification_results.extend(results)
            try:
                self._state.save_run(run)
                self._append(
                    run_id,
                    "VERIFICATION_RECORDED",
                    payload={
                        "verification_ids": [result.verification_id for result in results],
                        "evidence_ids": [item.evidence_ref.evidence_id for item in evidence],
                        "verifier_versions": sorted({result.verifier_version for result in results}),
                    },
                )
            except Exception:
                self._state.save_run(previous)
                raise

    def record_artifact(self, run_id: str, artifact: ArtifactRef) -> None:
        with self._lock:
            run = self._state.get_run(run_id)
            previous = deepcopy(run)
            run.artifacts.append(artifact)
            try:
                self._state.save_run(run)
                self._append(
                    run_id,
                    "ARTIFACT_RECORDED",
                    payload={
                        "artifact_id": artifact.artifact_id,
                        "kind": artifact.kind,
                        "location": artifact.location,
                        "sha256": artifact.sha256,
                    },
                )
            except Exception:
                self._state.save_run(previous)
                raise

    def record_loop_event(self, run_id: str, phase: LoopPhase, payload: dict[str, object]) -> None:
        with self._lock:
            self._append(run_id, f"AUTONOMY_{phase.value}", payload=payload)

    def _append(self, run_id: str, event_type: str, *, payload: dict[str, object]) -> Event:
        event = Event(
            event_id=str(uuid4()),
            run_id=run_id,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            sequence=self._events.next_sequence(run_id),
            payload=payload,
        )
        return self._events.append(event)


class AutonomousEngineeringLoop:
    """Execute the Phase 10 objective-to-evidence control loop.

    The loop is deliberately provider-agnostic. A reasoning provider proposes
    orientation and structured intents; policy authorizes; the broker executes;
    independent verification proves; the controller and bounded-autonomy layer
    decide whether another iteration is permitted. No model output is treated
    as proof or authority.
    """

    VERSION = "autonomous-engineering-loop-v1"

    def __init__(
        self,
        *,
        run_manager,
        state_store: StateStore,
        event_store: EventStore,
        context_engine: ContextEngine,
        controller: Controller,
        policy: PolicyEvaluator,
        broker: ExecutionBroker,
        verifier: IndependentVerifier,
        reasoning: ReasoningProvider,
        acceptance: AcceptanceCriteria,
        verification_plan: FrozenVerificationPlan,
        verification_environment: VerificationEnvironment,
        workspace: WorkspaceRuntime,
        budget,
        bounded_autonomy: BoundedAutonomy | None = None,
        observer=None,
        max_cycles: int = 32,
        lease_ttl_seconds: int = 300,
    ) -> None:
        if max_cycles <= 0:
            raise ValueError("max_cycles must be positive")
        if lease_ttl_seconds <= 0:
            raise ValueError("lease_ttl_seconds must be positive")
        if acceptance.objective_digest != verification_plan.objective_digest:
            raise ValueError("acceptance criteria and verification plan are bound to different objectives")
        if verification_environment.workspace != workspace.workspace.resolve():
            raise ValueError("verification environment must target the run workspace")

        self.run_manager = run_manager
        self._state_store = state_store
        self._event_store = event_store
        self._context = context_engine
        self._controller = controller
        self._policy = policy
        self._broker = broker
        self._verifier = verifier
        self._reasoning = reasoning
        self._acceptance = acceptance
        self._verification_plan = verification_plan
        self._verification_environment = verification_environment
        self._workspace = workspace
        self._budget = budget
        self._bounded = bounded_autonomy or BoundedAutonomy()
        self._observer = observer or NullLoopObserver()
        self._max_cycles = max_cycles
        self._lease_ttl = lease_ttl_seconds
        self._acceptor = WorkerResultAcceptor(
            run_manager.lease_manager,
            state_store=state_store,
            event_store=event_store,
        )
        self._recorder = _RunStateRecorder(state_store, event_store)
        self._orientation = ""
        self._plan: EngineeringPlan | None = None
        self._intent_cursor = 0
        self._last_verification = ()
        self._last_evidence = ()
        self._progress: list[ProgressMeasurement] = []
        self._previous_workspace_digest = self._workspace_digest()

    def run(self, run_id: str) -> LoopResult:
        for cycle in range(1, self._max_cycles + 1):
            run = self.run_manager.get_run(run_id)
            self._observer.observe(phase=LoopPhase.OBJECTIVE, run_id=run_id, payload={"state": run.state.value})
            self._recorder.record_loop_event(run_id, LoopPhase.OBJECTIVE, {"cycle": cycle, "state": run.state.value})

            if run.state is RunState.COMPLETE:
                return LoopResult(run_id, LoopPhase.COMPLETE, cycle, True, False, False, "run already complete", tuple(self._progress))
            if run.state in {RunState.ABORTED, RunState.EXPIRED}:
                return LoopResult(run_id, LoopPhase.STOP, cycle, False, False, True, f"terminal state: {run.state.value}", tuple(self._progress))
            if run.state is RunState.WAITING_HUMAN:
                return LoopResult(run_id, LoopPhase.WAIT_HUMAN, cycle, False, True, False, "human authority required", tuple(self._progress))

            limit = self._bounded.assess(run, self._budget, strategy_id=self._plan.strategy_id if self._plan else None)
            if limit.action is LimitAction.ABORT:
                if run.state is not RunState.RECOVERING:
                    self.run_manager.recover_run(run_id)
                self.run_manager.abort_run(run_id, limit.reason, actor=__import__("vajra.control.transition_authority", fromlist=["TransitionActor"]).TransitionActor.RECOVERY)
                return LoopResult(run_id, LoopPhase.STOP, cycle, False, False, True, limit.reason, tuple(self._progress))
            if limit.action is LimitAction.WAIT_HUMAN:
                if run.state is not RunState.WAITING_HUMAN:
                    self.run_manager.transition(run_id, RunState.WAITING_HUMAN, __import__("vajra.control.transition_authority", fromlist=["TransitionActor"]).TransitionActor.CONTROLLER, reason=limit.reason)
                return LoopResult(run_id, LoopPhase.WAIT_HUMAN, cycle, False, True, False, limit.reason, tuple(self._progress))

            if run.state is RunState.CREATED:
                self._controller.authorize_decision(run, self._controller.decide(run))
                self.run_manager.transition(run_id, RunState.QUEUED, __import__("vajra.control.transition_authority", fromlist=["TransitionActor"]).TransitionActor.CONTROLLER, reason="Phase 10 loop start")
                continue
            if run.state is RunState.QUEUED:
                self.run_manager.transition(run_id, RunState.ORIENTING, __import__("vajra.control.transition_authority", fromlist=["TransitionActor"]).TransitionActor.CONTROLLER, reason="begin orientation")
                continue
            if run.state is RunState.ORIENTING:
                self._orient(run)
                self.run_manager.transition(run_id, RunState.PLANNING, __import__("vajra.control.transition_authority", fromlist=["TransitionActor"]).TransitionActor.CONTROLLER, reason="orientation completed")
                continue
            if run.state is RunState.PLANNING:
                self._plan_for(run)
                self.run_manager.transition(run_id, RunState.EXECUTING, __import__("vajra.control.transition_authority", fromlist=["TransitionActor"]).TransitionActor.CONTROLLER, reason="structured plan ready")
                continue
            if run.state is RunState.EXECUTING:
                if self._plan is None:
                    raise AutonomousLoopError("EXECUTING without a structured plan")
                if self._intent_cursor >= len(self._plan.intents):
                    self.run_manager.transition(run_id, RunState.VERIFYING, __import__("vajra.control.transition_authority", fromlist=["TransitionActor"]).TransitionActor.CONTROLLER, reason="plan intents exhausted")
                    continue
                self._execute_intent(run, self._plan.intents[self._intent_cursor])
                self._intent_cursor += 1
                self.run_manager.transition(run_id, RunState.VERIFYING, __import__("vajra.control.transition_authority", fromlist=["TransitionActor"]).TransitionActor.CONTROLLER, reason="execution completed; independent verification required")
                continue
            if run.state is RunState.VERIFYING:
                self._verify(run)
                self.run_manager.transition(run_id, RunState.CANDIDATE, __import__("vajra.control.transition_authority", fromlist=["TransitionActor"]).TransitionActor.CONTROLLER, reason="verification completed")
                continue
            if run.state is RunState.CANDIDATE:
                decision = self._evaluate_candidate(run)
                if decision == "COMPLETE":
                    self.run_manager.transition(run_id, RunState.PROMOTION, __import__("vajra.control.transition_authority", fromlist=["TransitionActor"]).TransitionActor.CONTROLLER, reason="acceptance criteria satisfied")
                elif decision == "WAIT_HUMAN":
                    self.run_manager.transition(run_id, RunState.WAITING_HUMAN, __import__("vajra.control.transition_authority", fromlist=["TransitionActor"]).TransitionActor.CONTROLLER, reason="acceptance/policy requires human authority")
                    return LoopResult(run_id, LoopPhase.WAIT_HUMAN, cycle, False, True, False, "human authority required", tuple(self._progress))
                else:
                    self.run_manager.recover_run(run_id)
                continue
            if run.state is RunState.RECOVERING:
                self._replan_after_recovery(run)
                self.run_manager.transition(run_id, RunState.PLANNING, __import__("vajra.control.transition_authority", fromlist=["TransitionActor"]).TransitionActor.CONTROLLER, reason="recovery produced a new bounded plan")
                continue
            if run.state is RunState.PROMOTION:
                if self._promote(run):
                    return LoopResult(run_id, LoopPhase.COMPLETE, cycle, True, False, False, "objective satisfied and promoted", tuple(self._progress))
                self.run_manager.transition(run_id, RunState.WAITING_HUMAN, __import__("vajra.control.transition_authority", fromlist=["TransitionActor"]).TransitionActor.CONTROLLER, reason="promotion policy requires human authority")
                return LoopResult(run_id, LoopPhase.WAIT_HUMAN, cycle, False, True, False, "promotion requires human authority", tuple(self._progress))
            if run.state in {RunState.FAILED, RunState.PAUSED}:
                self.run_manager.recover_run(run_id)
                continue

        run = self.run_manager.get_run(run_id)
        return LoopResult(run_id, LoopPhase.STOP, self._max_cycles, False, run.state is RunState.WAITING_HUMAN, True, "Phase 10 cycle bound exhausted", tuple(self._progress))

    def _orient(self, run: EngineeringRun) -> None:
        self._emit(LoopPhase.CONTEXT, run.run_id, {})
        context = self._build_context(run)
        self._orientation = self._reasoning.orient(context)
        if not self._orientation.strip():
            raise AutonomousLoopError("reasoning provider returned empty orientation")
        self._emit(LoopPhase.ORIENT, run.run_id, {"orientation_digest": _digest(self._orientation), "context_digest": context.digest})

    def _plan_for(self, run: EngineeringRun) -> None:
        context = self._build_context(run)
        plan = self._reasoning.plan(context, self._orientation)
        if plan.context_digest != context.digest:
            raise AutonomousLoopError("reasoning plan was generated from stale or different context")
        self._plan = plan
        self._intent_cursor = 0
        self._emit(LoopPhase.PLAN, run.run_id, {"plan_id": plan.plan_id, "context_digest": plan.context_digest, "intent_count": len(plan.intents)})

    def _replan_after_recovery(self, run: EngineeringRun) -> None:
        context = self._build_context(run)
        previous = self._plan
        if previous is None:
            raise AutonomousLoopError("recovery requires a previous plan")
        reason = "verification or execution did not establish acceptable progress"
        self._plan = self._reasoning.replan(context, previous, reason)
        if self._plan.context_digest != context.digest:
            raise AutonomousLoopError("replan was generated from stale or different context")
        self._intent_cursor = 0
        self._orientation = "replanned after recovery"
        self._emit(LoopPhase.PLAN, run.run_id, {"replan": True, "plan_id": self._plan.plan_id, "context_digest": context.digest})

    def _execute_intent(self, run: EngineeringRun, planned: PlannedIntent) -> None:
        step_id = f"step-{planned.intent_id}"
        if not any(step.step_id == step_id for step in run.steps):
            self.run_manager.add_step(run.run_id, step_id, planned.operation)
        attempt_id = f"attempt-{uuid4()}"
        worker_id = "phase10-local-worker"
        lease_id = f"lease-{uuid4()}"
        self.run_manager.start_attempt(run.run_id, step_id, attempt_id, worker_id, lease_id, lease_ttl_seconds=self._lease_ttl)
        lease = self.run_manager.get_lease(attempt_id)
        if lease is None:
            raise AutonomousLoopError("execution lease disappeared before dispatch")

        intent = planned.to_intent(run_id=run.run_id, step_id=step_id, attempt_id=attempt_id)
        self._emit(LoopPhase.INTENT, run.run_id, {"intent_id": intent.intent_id, "operation": intent.operation, "strategy_id": planned.strategy_id})
        decision = self._policy.evaluate(intent)
        self._emit(LoopPhase.POLICY, run.run_id, {"intent_id": intent.intent_id, "decision": decision.decision.value, "reason": decision.reason})
        if decision.decision.value == "HUMAN_REQUIRED":
            self.run_manager.fail_attempt(run.run_id, step_id, attempt_id, decision.reason)
            self.run_manager.recover_run(run.run_id)
            raise AutonomousLoopError("intent requires human authority")
        if decision.decision.value == "DENY":
            self.run_manager.fail_attempt(run.run_id, step_id, attempt_id, decision.reason)
            self.run_manager.recover_run(run.run_id)
            return

        self._emit(LoopPhase.EXECUTE, run.run_id, {"intent_id": intent.intent_id})
        result = self._broker.execute(ExecutionRequest(intent=intent, policy_decision=decision))
        status = "SUCCEEDED" if result.status is ExecutionStatus.ACCEPTED and not result.errors else "FAILED"
        artifact = self._workspace_artifact(run.run_id, step_id)
        worker_result = WorkerResult(
            status=status,
            correlation_id=lease.lease_id,
            structured_result=dict(result.output),
            artifacts=(artifact,),
            errors=tuple(result.errors),
        )
        identity = WorkerExecutionIdentity(
            run_id=run.run_id,
            step_id=step_id,
            attempt_id=attempt_id,
            worker_id=worker_id,
            lease_id=lease.lease_id,
            fencing_token=lease.fencing_token,
            correlation_id=lease.lease_id,
        )
        self._acceptor.accept(identity, worker_result)
        self._emit(LoopPhase.OBSERVE, run.run_id, {"intent_id": intent.intent_id, "status": status, "artifact_id": artifact.artifact_id})
        if status == "FAILED":
            self.run_manager.recover_run(run.run_id)

    def _verify(self, run: EngineeringRun) -> None:
        step_id = run.current_step_id or "phase10-verification"
        attempt_id = self._current_attempt_id(run)
        self._emit(LoopPhase.VERIFY, run.run_id, {"plan_id": self._verification_plan.plan_id, "plan_digest": self._verification_plan.integrity_digest})
        report = self._verifier.verify(
            self._verification_plan,
            run_id=run.run_id,
            step_id=step_id,
            attempt_id=attempt_id,
            environment=self._verification_environment,
        )
        self._last_verification = report.verification_results
        self._last_evidence = report.evidence
        self._recorder.record_verification(run.run_id, report.verification_results, report.evidence)

        before = self._previous_workspace_digest
        after = self._workspace_digest()
        passed = sum(result.status.value == "PASSED" for result in report.verification_results)
        failed = sum(result.status.value == "FAILED" for result in report.verification_results)
        inconclusive = sum(result.status.value == "INCONCLUSIVE" for result in report.verification_results)
        measurement = ProgressMeasurement(
            before_digest=before,
            after_digest=after,
            verification_passed=passed,
            verification_failed=failed,
            verification_inconclusive=inconclusive,
            artifact_refs=tuple(artifact.artifact_id for artifact in self.run_manager.get_run(run.run_id).artifacts[-4:]),
            evidence_refs=tuple(item.evidence_ref.evidence_id for item in report.evidence),
        )
        self._progress.append(measurement)
        self._previous_workspace_digest = after
        self._emit(LoopPhase.MEASURE_PROGRESS, run.run_id, {"changed": measurement.changed, "verification_passed": passed, "verification_failed": failed, "verification_inconclusive": inconclusive})

        observation = ProgressObservation(
            run_id=run.run_id,
            step_id=step_id,
            attempt_id=attempt_id,
            state_digest=after,
            patch_digest=_git_digest("diff", self._workspace.workspace),
            test_signature=_digest("|".join(result.status.value for result in report.verification_results)),
            error_signature=_digest("|".join(";".join(result.check.get("reason", "") for result.check in result.checks if isinstance(result.check, dict)) for result in report.verification_results)),
        )
        bounded = self._bounded.assess(run, self._budget, progress=observation, strategy_id=self._plan.strategy_id if self._plan else None)
        if bounded.action is LimitAction.WAIT_HUMAN:
            self.run_manager.transition(run.run_id, RunState.WAITING_HUMAN, __import__("vajra.control.transition_authority", fromlist=["TransitionActor"]).TransitionActor.CONTROLLER, reason=bounded.reason)
            raise AutonomousLoopError(bounded.reason)
        if bounded.action is LimitAction.ABORT:
            self.run_manager.recover_run(run.run_id)
            self.run_manager.abort_run(run.run_id, bounded.reason, actor=__import__("vajra.control.transition_authority", fromlist=["TransitionActor"]).TransitionActor.RECOVERY)
            raise AutonomousLoopError(bounded.reason)

    def _evaluate_candidate(self, run: EngineeringRun) -> str:
        predicate_results: dict[str, PredicateResult] = {}
        by_id = {result.verification_id: result for result in self._last_verification}
        for check in self._verification_plan.checks:
            result = by_id.get(check.check_id)
            predicate_results[check.predicate_id] = (
                PredicateResult.TRUE if result and result.status.value == "PASSED" else
                PredicateResult.FALSE if result and result.status.value == "FAILED" else
                PredicateResult.INCONCLUSIVE
            )
        evidence_kinds = {item.evidence_ref.kind for item in self._last_evidence}
        evaluation = AcceptanceEvaluator().evaluate(self._acceptance, predicate_results, evidence_kinds)
        self._emit(LoopPhase.DECIDE_NEXT_STEP, run.run_id, {"acceptance_result": evaluation.result.value, "failed": list(evaluation.failed_predicates), "inconclusive": list(evaluation.inconclusive_predicates)})
        if evaluation.result is PredicateResult.TRUE:
            return "COMPLETE"
        if evaluation.result is PredicateResult.INCONCLUSIVE and not self._plan:
            return "WAIT_HUMAN"
        if evaluation.result is PredicateResult.FALSE and self._plan is not None:
            return "RECOVER"
        return "WAIT_HUMAN"

    def _promote(self, run: EngineeringRun) -> bool:
        intent = __import__("vajra.policy.contracts", fromlist=["Intent"]).Intent(
            intent_id=f"promotion-{run.run_id}",
            run_id=run.run_id,
            step_id=run.current_step_id or "promotion",
            attempt_id=self._current_attempt_id(run),
            operation="PROMOTE_RUN",
            parameters={"objective_digest": self._acceptance.objective_digest},
            reason="promote verified candidate",
        )
        decision = self._policy.evaluate(intent)
        self._emit(LoopPhase.POLICY, run.run_id, {"promotion": True, "decision": decision.decision.value})
        if decision.decision.value != "ALLOW":
            return False
        predicate_results = {check.predicate_id: PredicateResult.TRUE for check in self._verification_plan.checks}
        evidence_kinds = {item.evidence_ref.kind for item in self._last_evidence}
        evaluation = AcceptanceEvaluator().evaluate(self._acceptance, predicate_results, evidence_kinds)
        artifact_refs = tuple(artifact.artifact_id for artifact in self.run_manager.get_run(run.run_id).artifacts)
        verification_refs = tuple(item.evidence_ref.evidence_id for item in self._last_evidence)
        self.run_manager.complete_run(
            run.run_id,
            evaluation,
            artifact_refs=artifact_refs,
            verification_refs=verification_refs,
            policy_approved=True,
            actor=__import__("vajra.control.transition_authority", fromlist=["TransitionActor"]).TransitionActor.SYSTEM,
            reason="Phase 10 evidence-bound promotion",
        )
        self._emit(LoopPhase.COMPLETE, run.run_id, {"artifact_refs": list(artifact_refs), "verification_refs": list(verification_refs)})
        return True

    def _build_context(self, run: EngineeringRun) -> ContextBundle:
        return self._context.build_bundle(
            run_id=run.run_id,
            workspace_id=self._workspace.workspace_id,
            repository_id=self._workspace.repository_id,
            objective=run.objective,
            workspace=self._workspace.workspace,
            revision=self._workspace.base_revision,
            acceptance_criteria=run.acceptance_criteria,
            allowed_capabilities=(),
            budget={"budget_id": self._budget.budget_id},
        )

    def _workspace_digest(self) -> str:
        from vajra.control.reality import filesystem_digest
        return filesystem_digest(self._workspace.workspace)

    def _workspace_artifact(self, run_id: str, step_id: str) -> ArtifactRef:
        status = _git_output("status", self._workspace.workspace)
        diff = _git_output("diff", self._workspace.workspace)
        payload = status + "\n---DIFF---\n" + diff
        digest = hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()
        artifact = ArtifactRef(
            artifact_id=f"artifact-{digest[:24]}",
            kind="workspace-diff",
            location=f"memory://phase10/{run_id}/{step_id}/{digest}",
            sha256=digest,
        )
        self._recorder.record_artifact(run_id, artifact)
        return artifact

    def _current_attempt_id(self, run: EngineeringRun) -> str:
        if run.current_step_id:
            for step in run.steps:
                if step.step_id == run.current_step_id and step.attempts:
                    return step.attempts[-1].attempt_id
        for step in reversed(run.steps):
            if step.attempts:
                return step.attempts[-1].attempt_id
        return "phase10-verification"

    def _emit(self, phase: LoopPhase, run_id: str, payload: dict[str, object]) -> None:
        self._observer.observe(phase=phase, run_id=run_id, payload=payload)
        self._recorder.record_loop_event(run_id, phase, payload)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _git_output(operation: str, workspace: Path) -> str:
    command = ("git", "diff", "--binary") if operation == "diff" else ("git", "status", "--porcelain", "--untracked-files=all")
    completed = subprocess.run(command, cwd=workspace, capture_output=True, text=True, check=False)
    return (completed.stdout + completed.stderr).replace("\x00", "")


def _git_digest(operation: str, workspace: Path) -> str:
    return _digest(_git_output(operation, workspace))
