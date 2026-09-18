# First Engineering Run

This is the canonical first-use procedure for VAJRA.

## Purpose

Run VAJRA against a disposable repository before pointing it at a real project. The harness exercises the Phase 10 autonomous control path:

objective → orientation → plan → intent → policy → broker → observation → independent verification → acceptance → promotion.

The first run intentionally uses a deterministic local reasoner and a minimal local file backend. It does **not** claim a production LLM, remote worker, or gVisor sandbox integration.

## Run it

From the VAJRA checkout:

```bash
cd ~/vajra
python -m scripts.first_engineering_run
```

If the repository is being used without an installed package, use:

```bash
cd ~/vajra
PYTHONPATH=src python scripts/first_engineering_run.py
```

The default disposable workspace is:

```
~/vajra-first-run
```

To choose another disposable location:

```bash
PYTHONPATH=src python scripts/first_engineering_run.py --workspace ~/vajra-first-run
```

## Expected result

A successful run ends with:

```
result: COMPLETE
```

and reports non-zero counts for steps, attempts, verification results, artifacts, and events.

The harness creates:

```
~/vajra-first-run/result.txt
```

with the content `done`.

## Safety boundary

Do not use `~/vajra` itself as the first-run workspace. The first run is a runtime smoke test of VAJRA's control loop, not a test of VAJRA's ability to safely modify its own source tree.

After this passes, the next step is a second controlled run against a disposable real project with a bounded engineering objective and an independently defined verification plan.
