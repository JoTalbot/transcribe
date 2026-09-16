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
```

A request contains `job_id`, `recording_id`, `stage`, `worker`, `lease_id`, and dependency artifact IDs when the stage has prerequisites. `input_artifact_id` remains the first dependency for backward compatibility.

A successful result contains `job_id`, `status=completed`, `artifact_id`, `worker`, and `lease_id`. A failed result contains `job_id`, `status=failed`, an error string, `worker`, and `lease_id`.

Writers use atomic replacement so readers do not intentionally consume partially written JSON files. The Colab consumer first moves a request into `processing/`, validates the persisted lease identity, processes it, publishes a result, and removes the processing record. The control plane accepts a result only when the worker and lease still match the PostgreSQL job ownership. Stale or foreign results are quarantined instead of being applied.

Completed artifacts are immutable exchange outputs with manifests containing artifact ID, recording ID, stage, size, checksum, producer, and model version. Production result application verifies the manifest, checksum, exchange-root confinement, recording binding, and stage binding before completing the PostgreSQL job.

## Production Colab worker

Mount Google Drive and run the GPU exchange worker against the canonical exchange root:

```bash
python scripts/colab_exchange_worker.py \
  --root /content/drive/MyDrive/transcribe/exchange \
  --input /content/drive/MyDrive/transcribe/input \
  --output /content/drive/MyDrive/transcribe/exchange/artifacts \
  --once
```

For continuous polling:

```bash
python scripts/colab_exchange_worker.py \
  --root /content/drive/MyDrive/transcribe/exchange \
  --input /content/drive/MyDrive/transcribe/input \
  --output /content/drive/MyDrive/transcribe/exchange/artifacts \
  --poll 30
```

The production worker requires a CUDA GPU and the Colab Secret `HUGGINGFACE_TOKEN`. It loads Whisper `large-v3`, `pyannote/speaker-diarization-3.1`, and the SpeechBrain ECAPA speaker encoder. ASR, diarization, and embeddings consume dependency artifacts by ID rather than trusting arbitrary paths.

The repository's notebook `notebooks/transcribe_pipeline.ipynb` is the canonical Colab setup and exchange entrypoint. CI validates that the notebook references this worker, canonical Drive paths, and the three production model families.

## Evidence collection

After a physical run, collect a machine-readable snapshot of the Colab environment and every exchange artifact. The collector records package versions, CUDA/GPU information, artifact IDs, model versions, sizes, SHA-256 values, and checksum verification status. It does not read or print authentication secrets.

```bash
python scripts/colab_gpu_evidence.py \
  --root /content/drive/MyDrive/transcribe/exchange/artifacts \
  --output /content/drive/MyDrive/transcribe/exchange/colab_gpu_evidence.json
```

Keep the resulting JSON together with the execution logs and fill `docs/COLAB_GPU_E2E_EVIDENCE_TEMPLATE_RU.md`. The collector is evidence tooling only: running it without a real GPU pipeline does not turn a dry-run into physical E2E proof.

## Dry-run versus physical E2E

The repository contains deterministic transport and cross-worker dry-run tests, but those do not constitute proof that real GPU inference completed in Google Colab. Physical E2E acceptance still requires an actual Oracle → Google Drive exchange → Colab CUDA inference → artifact publication → Oracle result application run, with measured timing, RAM/VRAM usage, artifact sizes, and repeat/recovery checks.

Authentication, browser sessions, CAPTCHA handling, and Google credentials are outside this exchange module. No credentials belong in the repository.
