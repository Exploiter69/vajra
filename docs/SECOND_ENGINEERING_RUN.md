# Engineering Run #2 — Real Disposable Project

Run #2 is the first VAJRA run against a real code project rather than a single synthetic artifact.

## Objective

VAJRA receives this bounded engineering objective:

> Add `multiply(a, b)` to `calculator.py` and add a regression test proving `multiply(6, 7) == 42`.

The disposable project starts as a small Git repository containing an existing `add()` implementation and one test. VAJRA must produce the code change and test, then an independently compiled verification plan runs the project's pytest suite.

## Run it

From the VAJRA checkout:

```bash
cd ~/vajra
git pull --ff-only origin main
PYTHONPATH=src python scripts/second_engineering_run.py
```

Default disposable project:

```
~/vajra-run-2-project
```

You may choose another disposable directory with `--workspace`.

## What this proves

Run #2 exercises:

objective → orientation → structured plan → multiple write intents → policy → execution broker → real project files → independent pytest verification → evidence → acceptance → promotion.

The project is real code with Git history and an actual test suite. The verification command is compiled before execution and is not supplied by the reasoner.

## What it does not prove

Run #2 still uses the deterministic `RealProjectReasoner`. It is therefore **not yet a Kaggle/Qwen model-backed run**.

It also uses the local reference execution backend rather than the gVisor worker path. Those are deliberate boundaries for this run.

## Safety

The default workspace is disposable. Do not point this harness at `~/vajra`, another production repository, or a valuable checkout.

A successful run should end with:

```
result: COMPLETE
```

and the disposable project's pytest verification should be recorded as passed evidence.
