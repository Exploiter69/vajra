from unittest.mock import Mock

from vajra.routing.contracts import ModelIdentity, ModelResult
from vajra.runtime.remote_reasoner import GatewayReasoner, ModelProposalError


def context():
    return Mock(
        query="add multiply",
        run_id="r",
        revision="rev",
        digest="d",
        repository_summary="calculator",
        relevant_files=("calculator.py", "test_calculator.py"),
        acceptance_criteria=("multiply exists",),
    )


def test_remote_reasoner_rejects_forbidden_operation():
    gateway = Mock()
    identity = ModelIdentity("kaggle", "qwen2.5-coder:32b", "ollama", "http-worker")
    gateway.invoke.return_value = ModelResult(
        status="SUCCEEDED",
        structured_output={"plan_id": "p", "strategy_id": "s", "intents": [{
            "intent_id": "x", "operation": "RUN_SHELL", "path": "calculator.py",
            "content": "bad", "reason": "bad"
        }]},
        model_identity=identity,
    )
    reasoner = GatewayReasoner(gateway, identity.canonical)
    try:
        reasoner.plan(context(), "implement")
    except ModelProposalError as exc:
        assert "forbidden operation" in str(exc)
    else:
        raise AssertionError("forbidden model operation was accepted")


def test_remote_reasoner_accepts_bounded_write_plan():
    gateway = Mock()
    identity = ModelIdentity("kaggle", "qwen2.5-coder:32b", "ollama", "http-worker")
    gateway.invoke.return_value = ModelResult(
        status="SUCCEEDED",
        structured_output={"response": '{"plan_id":"p","strategy_id":"s","intents":[{"intent_id":"x","operation":"WRITE_FILE","path":"calculator.py","content":"def multiply(a,b):\\n    return a*b\\n","reason":"implement multiply"}]}'},
        model_identity=identity,
    )
    reasoner = GatewayReasoner(gateway, identity.canonical)
    plan = reasoner.plan(context(), "implement")
    assert len(plan.intents) == 1
    assert plan.intents[0].operation == "WRITE_FILE"
    assert plan.intents[0].parameters["path"] == "calculator.py"
