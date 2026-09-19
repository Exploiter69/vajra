# VAJRA Qwen3-Coder Kaggle Worker

## Purpose

This is the canonical free Kaggle worker path for VAJRA's remote model execution.

- Model: Qwen3-Coder-30B-A3B-Instruct
- Quantization: Q4_K_M GGUF
- Runtime: llama.cpp CUDA
- Hardware target: 2x Tesla T4
- VAJRA protocol: `vajra-worker-v1`
- Worker API: `/health`, `/capabilities`, `/infer`
- Authority: proposal-only; VAJRA remains authoritative for policy, execution, verification, and Run state.

The Q4_K_M GGUF used by the notebook is the TensorBlock conversion of the Qwen model. Its published size is about 18.6 GB and it is described as a balanced/recommended quantization.

## Notebook

Use only:

`infra/kaggle/vajra_qwen3_coder_t4x2.ipynb`

Kaggle settings:

1. Accelerator: **2x T4 GPU**
2. Internet: **On**
3. Open the notebook.
4. Run its single operational cell.

The cell is intentionally self-contained. It:

1. verifies the two T4 GPUs;
2. downloads a shallow source archive of the VAJRA main branch;
3. downloads/reuses the Q4_K_M GGUF;
4. discovers and downloads the pinned llama.cpp b10982 Ubuntu CUDA 13 x64 release asset;
5. starts llama.cpp with both GPUs using layer splitting;
6. starts the VAJRA worker adapter;
7. validates health and capabilities;
8. performs a real `vajra-worker-v1` inference and checks the correlation ID;
9. remains attached to the llama.cpp process so the worker remains alive while the Kaggle runtime/cell remains alive.

This is runtime persistence, not permanent compute. Kaggle can reclaim or destroy a free runtime.

## Expected terminal state

The final section should print:

```
=== VAJRA QWEN3-CODER WORKER READY ===
worker=http://127.0.0.1:8787
llama=http://127.0.0.1:8000
model=Qwen3-Coder-30B-A3B-Instruct-Q4_K_M
Keep this cell running while VAJRA uses the worker.
```

The protocol smoke must also show a completed result whose correlation ID is:

`kaggle-qwen3-correlation-001`

and whose response contains:

`VAJRA_QWEN3_CODER_OK`

## Connecting the VAJRA control plane

Once the notebook's local smoke passes, expose the worker temporarily and set:

```bash
export VAJRA_KAGGLE_WORKER_URL="https://<temporary-worker-host>/infer"
export VAJRA_WORKER_MODEL="Qwen3-Coder-30B-A3B-Instruct-Q4_K_M"
```

Then Run #3 uses the existing `HTTPWorkerProvider` and `RemoteWorkerModelAdapter`. The control plane first verifies `/health` and `/capabilities`; model output never receives Run-state authority.

## Validation order

Do not start with the full engineering run.

1. Kaggle GPU check.
2. llama.cpp device/model load.
3. VAJRA worker health.
4. VAJRA protocol smoke.
5. Temporary remote endpoint health from the laptop.
6. One direct remote `WorkerJob`.
7. Full VAJRA Run #3.
8. Independent verification and full local test suite.

This order keeps model/runtime failures separate from VAJRA control-plane failures.
