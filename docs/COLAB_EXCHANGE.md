# Colab exchange contract

The control plane and GPU worker communicate through a filesystem contract. In Google Colab, the exchange root can live under a mounted Google Drive directory.

## Layout

```text
transcribe/exchange/
  jobs/<job_id>.json
  processing/<job_id>.json
  results/<job_id>.json
```

A request contains `job_id`, `recording_id`, `stage`, and optionally `input_artifact_id`.
A successful result contains `job_id`, `status=completed`, and `artifact_id`. A failed result contains `job_id`, `status=failed`, and an error string.

Writers use atomic replacement so readers never intentionally consume a partially written JSON file. The Colab consumer first moves a request into `processing/`, processes it, publishes a result, and removes the processing record.

## Colab

Mount Google Drive and point the worker at the exchange directory:

```bash
python scripts/colab_exchange_worker.py --root /content/drive/MyDrive/transcribe/exchange --once
```

For continuous polling:

```bash
python scripts/colab_exchange_worker.py --root /content/drive/MyDrive/transcribe/exchange --poll 30
```

The current CLI processor is deliberately a dry-run processor. It validates the transport lifecycle without pretending that inference happened. The production processor will invoke the existing Whisper + pyannote notebook/runtime and publish immutable artifact manifests.

Authentication, browser sessions, CAPTCHA handling, and Google credentials are outside this exchange module. No credentials belong in the repository.
