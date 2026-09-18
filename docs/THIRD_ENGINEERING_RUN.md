# VAJRA Engineering Run #3

Run #3 is the first engineering run whose reasoning proposal is produced by the
real Qwen 2.5 Coder 32B worker path:

`VAJRA -> ModelGateway -> HTTP worker -> Ollama -> Qwen 2.5 Coder 32B`.

The model remains proposal-only. VAJRA policy, the execution broker,
independent verification, acceptance evaluation, and promotion remain
authoritative.

## Readiness gate

Run #3 now performs a worker readiness preflight **before creating or mutating
the disposable project**.

The provider-neutral boundary checks:

- `GET /health`;
- worker protocol version;
- advertised model identity;
- `GET /capabilities`;
- advertised worker capabilities.

If the worker is unavailable or mismatched, the command exits without making a
project change and reports the reason.

## Kaggle lifecycle limitation

The readiness boundary is intentionally separate from worker provisioning.

The current Kaggle worker server is a process running inside a Kaggle runtime.
VAJRA can verify an already-exposed endpoint, but the repository does not claim
that it can autonomously create and maintain a Kaggle interactive notebook
session.

The Kaggle CLI can push a kernel and trigger a kernel run, but that is not the
same contract as an always-on HTTP worker endpoint. Therefore Run #3 must not
pretend that `kaggle kernels push` has solved worker endpoint lifecycle.

VAJRA now has a composed `KaggleManagedWorkerProvider`: the Kaggle launcher owns
start/stop mechanics, while `HTTPWorkerProvider` independently proves `/health`
and `/capabilities` before `ManagedWorkerProvider` creates a lease. This closes
the software lifecycle composition without claiming that Kaggle itself exposes
the notebook's HTTP port publicly.

For a genuinely unattended worker, a provider adapter must own:

1. discover;
2. provision/start;
3. wait for readiness;
4. expose or return the worker endpoint;
5. monitor liveness;
6. release/stop;
7. recover after worker loss.

Those operations must remain outside the model gateway and must never become
model authority.

## Current zero-cost operating modes

### Local worker

A local Ollama worker can be kept available while the laptop is running.
This is the simplest fully controlled provider.

### Kaggle burst worker

A Kaggle runtime can provide the validated Qwen/T4 inference capability when
its worker endpoint is actually running and reachable. Run #3 accepts that
endpoint only after the readiness gate passes.

### Future provider adapter

A provider adapter may automate lifecycle when the provider exposes a stable
programmatic mechanism for the required runtime and endpoint. The adapter must
not depend on browser clicking as the core VAJRA control-plane mechanism.

## Run command

After the worker endpoint is genuinely ready:

```bash
cd ~/vajra
git pull --ff-only origin main
rm -rf ~/vajra-run-3-project
VAJRA_KAGGLE_WORKER_URL="https://<ready-worker>/infer" PYTHONPATH=src python scripts/third_engineering_run.py
```

The command will fail fast if `/health` or `/capabilities` cannot prove that
the expected Qwen worker is ready.

## Authority chain

```
Qwen proposes
    ↓
ModelGateway transports proposal
    ↓
VAJRA controller/policy decides
    ↓
ExecutionBroker performs authorized mutation
    ↓
IndependentVerifier proves the result
    ↓
Acceptance evaluator decides candidate status
    ↓
VAJRA promotion authority completes the run
```

The remote model never receives authority to mutate the repository, change
canonical Run state, approve its own work, or promote a Run.
