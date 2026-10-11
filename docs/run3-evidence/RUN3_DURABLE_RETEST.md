# Run #3 — durable local controller + Kaggle inference retest

This retest changes the controller's canonical run/event backend to SQLite. Kaggle remains an ephemeral proposal-only inference worker; it never owns canonical VAJRA state.

## What this proves

- The Run #3 harness writes canonical run snapshots and lifecycle events to one SQLite database.
- Run #3 preflights pytest before contacting the worker or mutating the workspace; missing pytest is reported as an environment prerequisite, not a code-test failure.
- Frozen acceptance checks require preserving the original `add()` API and its test while adding multiplication.
- Command verification evidence stores the bounded output excerpt, output digest, command, exit code, and sanitized environment metadata in the durable run/event record.
- Missing test runners/commands are classified as inconclusive, and repeated identical command failures stop for human diagnosis instead of cycling indefinitely.
- Accepted worker results transition their step state to `COMPLETE`; failed results transition the step to `RECOVERING`.
- State and event writes made through RunManager, the loop evidence recorder, and worker-result acceptance share a transaction when they use the same SQLiteRunStore.
- SQLite can be closed and reopened without losing the persisted run snapshot or event sequence.
- Remote inference requires a bearer token of at least 32 characters. Health/capability discovery is public metadata; `POST /infer` is authenticated.

This does **not** yet prove automatic continuation of an interrupted autonomous loop. The reasoning plan and in-process intent cursor are not yet restored from durable checkpoints. A persisted Run is not, by itself, proof that every in-flight operation is safely resumable.

## Kaggle worker steps

1. Open `infra/kaggle/vajra_qwen3_coder_t4x2.ipynb` from the merged `main` branch.
2. In Kaggle Notebook Secrets, add `VAJRA_WORKER_TOKEN` with a randomly generated value of at least 32 characters. Keep the value private and use the same value on the local controller.
3. Run cells in order. Cell 1 builds llama.cpp natively for T4 (SM 75), downloads the Qwen GGUF, and starts inference. Cell 2 starts the authenticated VAJRA worker. Cell 3 verifies a real authenticated worker-protocol inference. Cell 4 starts a temporary Cloudflare quick tunnel.
4. Copy the printed `infer_url`. Do not publish the token or save it in notebook output.

## Local VAJRA controller

After this PR is merged, on the Omarchy laptop:

```bash
cd ~/vajra
git pull --ff-only origin main
source .venv/bin/activate
python -m pip install -e '.[dev]'
export VAJRA_WORKER_TOKEN='<the same private token configured in Kaggle>'
export VAJRA_KAGGLE_WORKER_URL='https://<the-printed-host>.trycloudflare.com/infer'
python scripts/third_engineering_run.py
```

The script uses `~/.local/state/vajra/run3.sqlite3` by default and prints the generated `run_id` and database path. It generates a timestamped run ID per invocation. Do not paste the secret into GitHub, source files, or chat.

## Post-run record check

After the script exits, use the printed run ID and database path:

```bash
python - <<'PY'
import os
from vajra.runtime.run_manager import RunManager
from vajra.runtime.sqlite_run_store import SQLiteRunStore

path = os.path.expanduser("~/.local/state/vajra/run3.sqlite3")
run_id = input("Run ID printed by VAJRA: ").strip()
with SQLiteRunStore(path) as store:
    manager = RunManager(state_store=store, event_store=store)
    run = manager.get_run(run_id)
    events = manager.events(run_id)
    print("state:", run.state.value)
    print("steps:", len(run.steps))
    print("events:", len(events))
    print("sequence:", [event.sequence for event in events])
PY
```

A successful task should report `COMPLETE`, include the independent test/verification evidence, and retain a contiguous event sequence after reopening the database. Preserve the terminal output separately as physical gate evidence. The first physical Kaggle retest is required because hosted CI cannot validate the live GPU, tunnel, or real Qwen response.
