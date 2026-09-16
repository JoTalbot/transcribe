# Colab exchange contract

The control plane and GPU worker communicate through a filesystem contract. In Google Colab, the exchange root lives under a mounted Google Drive directory.

## Layout

```text
transcribe/exchange/
  requests/<job_id>.json
  processing/<job_id>.json
  results/<job_id>.json
  results/quarantine/<job_id>.json
  artifacts/<recording_id>/...
  artifacts/metrics/worker-metrics-<run>.json
```

A request contains `job_id`, `recording_id`, `stage`, `worker`, `lease_id`, and dependency artifact IDs when the stage has prerequisites. `input_artifact_id` remains the first dependency for backward compatibility.

A successful result contains `job_id`, `status=completed`, `artifact_id`, `worker`, and `lease_id`. A failed result contains `job_id`, `status=failed`, an error string, `worker`, and `lease_id`.

Exchange JSON writers use atomic replacement so readers do not intentionally consume partially written JSON files. Artifact manifests use exclusive creation and immutable identity: the first writer wins, identical repeats are idempotent, and a concurrent writer with different content is rejected rather than replacing the published manifest. The Colab consumer first moves a request into `processing/`, validates the persisted lease identity, processes it, publishes a result, and removes the processing record. The control plane accepts a result only when the worker and lease still match the PostgreSQL job ownership. Stale or foreign results are quarantined instead of being applied.

Completed artifacts are immutable exchange outputs with manifests containing artifact ID, recording ID, stage, size, checksum, producer, and model version. Production result application verifies the manifest, checksum, exchange-root confinement, recording binding, and stage binding before completing the PostgreSQL job.

## Production Colab worker

Mount Google Drive and run the GPU exchange worker against the canonical exchange root:

```bash
python scripts/colab_exchange_worker.py \
  --root /content/drive/MyDrive/transcribe/exchange \
  --input /content/drive/MyDrive/transcribe/input \
  --output /content/drive/MyDrive/transcribe/exchange/artifacts \
  --metrics-output /content/drive/MyDrive/transcribe/exchange/artifacts/metrics \
  --once
```

For continuous polling:

```bash
python scripts/colab_exchange_worker.py \
  --root /content/drive/MyDrive/transcribe/exchange \
  --input /content/drive/MyDrive/transcribe/input \
  --output /content/drive/MyDrive/transcribe/exchange/artifacts \
  --metrics-output /content/drive/MyDrive/transcribe/exchange/artifacts/metrics \
  --poll 30
```

The `--once` form is the preferred production validation mode for a managed Colab runtime. Continuous polling should only be used where the selected Colab runtime/product permits the workload. Google's current Colab FAQ states that free managed runtimes restrict distributed-computing workers and remote-control/web-UI patterns; resource availability and runtime lifetime are also not guaranteed. Do not treat `scripts/colab_worker.py` or the Playwright browser adapter as a way to bypass those restrictions. For guaranteed or continuously managed execution, use an appropriate paid Colab/GCP offering or a controlled local runtime instead.

The production worker requires a CUDA GPU and the Colab Secret `HUGGINGFACE_TOKEN`. It loads Whisper `large-v3`, `pyannote/speaker-diarization-3.1`, and the SpeechBrain ECAPA speaker encoder. ASR, diarization, and embeddings consume dependency artifacts by ID rather than trusting arbitrary paths.

The repository's notebook `notebooks/transcribe_pipeline.ipynb` is the canonical Colab setup and exchange entrypoint. CI validates that the notebook references this worker, canonical Drive paths, and the three production model families.

## Runtime evidence

When `--metrics-output` is supplied, the worker writes an immutable `worker-metrics-<run>.json` snapshot after the run. It records model-load timings for Whisper, diarization, and ECAPA, total wall-clock time, maximum process RSS, and per-job stage duration/status. The snapshot contains no authentication secrets.

This evidence is deliberately separate from artifact manifests. It can be collected after the run and retained with the execution logs. In continuous mode, each worker process writes a unique snapshot instead of replacing an earlier run.

## Evidence collection

After a physical run, collect a machine-readable snapshot of the Colab environment, runtime measurements, and every exchange artifact. The collector records package versions, CUDA/GPU information, worker timing/memory metrics, artifact IDs, model versions, sizes, SHA-256 values, and checksum verification status. It does not read or print authentication secrets.

```bash
python scripts/colab_gpu_evidence.py \
  --root /content/drive/MyDrive/transcribe/exchange/artifacts \
  --output /content/drive/MyDrive/transcribe/exchange/colab_gpu_evidence.json
```

Keep the resulting JSON together with the execution logs and fill `docs/COLAB_GPU_E2E_EVIDENCE_TEMPLATE_RU.md`. The collector is evidence tooling only: running it without a real GPU pipeline does not turn a dry-run into physical E2E proof.

## Artifact reconciliation audit

The exchange artifact store has a read-only integrity audit for operational recovery and post-run verification. It scans manifests, detects duplicate artifact IDs, validates payload size and SHA-256, checks exchange-root confinement, and reports missing or orphan payloads. It never deletes or rewrites artifacts.

```bash
python scripts/audit_artifacts.py \
  --root /content/drive/MyDrive/transcribe/exchange/artifacts
```

Use `--json` for machine-readable evidence. A non-zero exit status means the audit found an integrity issue and should block production acceptance until the artifact store is investigated.

## Dry-run versus physical E2E

The repository contains deterministic transport and cross-worker dry-run tests, but those do not constitute proof that real GPU inference completed in Google Colab. Physical E2E acceptance still requires an actual Oracle → Google Drive exchange → Colab CUDA inference → artifact publication → Oracle result application run, with measured model-load/stage timing, RAM/VRAM usage, artifact sizes, and repeat/recovery checks.

Authentication, browser sessions, CAPTCHA handling, and Google credentials are outside this exchange module. No credentials belong in the repository.
