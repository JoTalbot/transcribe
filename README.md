# Transcribe: Whisper large-v3 + speaker diarization

Automated audio transcription with speaker diarization. Heavy inference runs in free Google Colab GPU; GitHub Actions validates the project and the Oracle scheduler coordinates durable PostgreSQL jobs through a Drive-compatible exchange.

## Architecture

```text
Audio corpus
    |
    v
build_manifest.py  ---> recording_id + exact relative path + SHA-256
    |
    v
Oracle / orchestrator
    |
    +--> PostgreSQL canonical state + stable jobs
    |
    +--> oracle_worker.py ---> Drive/exchange/requests/*.json
                               |
                               v
                        Colab GPU worker
                        Whisper + Pyannote + ECAPA
                               |
                               +--> exchange/processing/*.json
                               |
                               +--> exchange/artifacts/*
                               |
                               v
                        exchange/results/*.json
                               |
                               v
                        Oracle result reconciliation
```

The manifest path is the source of truth for locating audio. A `recording_id` is derived from the relative path, so the worker must not assume that the ID is the original filename. Exchange envelopes therefore carry the exact `input_path` when a stage has no artifact dependency.

The orchestration layer keeps the logical stages resumable and idempotent. PostgreSQL is the canonical execution state; local JSON exchange state is transport only and is never the production source of truth. The canonical Colab exchange worker performs GPU-heavy ASR/diarization and speaker-embedding work; the broader 24-stage intelligence roadmap remains a target architecture rather than a claim that every stage is already implemented.

### Canonical exchange layout

```text
exchange/
├── requests/       # atomic job envelopes published by the orchestrator
├── processing/     # claimed requests while a Colab worker owns a lease
├── results/        # atomic result envelopes awaiting PostgreSQL reconciliation
├── artifacts/      # stage artifacts and manifests used by downstream stages
└── results/quarantine/  # malformed, stale, foreign, or orphaned records
```

Requests and results are written atomically. PostgreSQL lease identity (`worker` + `lease_id`) is carried through the exchange and checked again before a result can change canonical state. This prevents a late worker from completing a job after its lease has been reclaimed.

### 5-minute Colab setup

The Colab notebook is the **GPU consumer**, not the queue seeder. A complete E2E run needs an Oracle/PostgreSQL job to exist before Colab can consume it.

1. Accept the model terms for `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0` on Hugging Face.
2. Create a Hugging Face access token with read access. In Colab open **Secrets**, create `HUGGINGFACE_TOKEN`, and allow notebook access.
3. Put a small test audio file into `MyDrive/transcribe/input`.
4. On the Oracle/control-plane side, build or refresh the manifest and seed the canonical PostgreSQL queue, then run `scripts/oracle_worker.py` so the GPU stages are published into `exchange/requests/`.
5. Open `notebooks/transcribe_pipeline.ipynb` in Colab and use **Runtime -> Run all**. The notebook mounts `MyDrive/transcribe/exchange` and invokes the canonical `scripts/colab_exchange_worker.py`.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/JoTalbot/transcribe/blob/main/notebooks/transcribe_pipeline.ipynb)

For a Colab-only smoke test, a valid request must already be present in `exchange/requests/`. Simply placing a WAV in `input/` does not create a PostgreSQL execution job or an exchange request.

## GitHub Actions secrets

For optional server-side Drive queue checks, add `GDRIVE_CREDENTIALS` containing a Google service-account JSON. Share the Drive `transcribe` folder with that service-account email. Do **not** commit credentials or Google cookies.

`HUGGINGFACE_TOKEN` is only needed by Colab and should normally live in Colab Secrets, not GitHub Actions.

## Exchange queue

First seed the canonical PostgreSQL queue from the manifest:

```bash
export TRANSCRIBE_DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/transcribe'
python scripts/run_pipeline.py --manifest state/manifest.json
```

For a dry planning/inspection run without dispatching workers:

```bash
python scripts/run_pipeline.py --manifest state/manifest.json --plan-only
```

Then run the persistent Oracle scheduler. It opens a fresh PostgreSQL connection for every cycle, applies exchange results before reclaiming stale leases, and dispatches only through the lease-aware scheduler:

```bash
export TRANSCRIBE_WORKER=oracle-1
python scripts/oracle_worker.py \
  --manifest state/manifest.json \
  --exchange /path/to/transcribe/exchange \
  --interval 15
```

For a single safe cycle:

```bash
python scripts/oracle_worker.py \
  --manifest state/manifest.json \
  --exchange /path/to/transcribe/exchange \
  --once
```

The daemon handles `SIGINT`/`SIGTERM` gracefully, logs transient cycle failures, continues with the normal interval, and does not keep a PostgreSQL connection open between cycles. This is intentional: a single temporary database or exchange failure must not kill the durable Oracle scheduler, while the error remains visible in the worker log.

The canonical Colab exchange worker watches `exchange/requests`, atomically claims requests into `processing`, validates the persisted worker/lease identity, runs GPU inference, writes `exchange/results`, and removes the processing marker after completion or failure.

The seeding command creates missing recordings and stable stage jobs in PostgreSQL and never overwrites an existing execution job. It also rejects a manifest path that conflicts with canonical database state. The dispatch command validates manifest paths against PostgreSQL and uses lease-aware scheduling, so repeated submission is safe.

## Outputs

Stage artifacts are stored under the canonical exchange artifact root and are addressed by stable artifact IDs. The final transcript representation contains speaker-labelled text and machine-readable metadata; exact filenames depend on the stage and recording ID.

## Optional Drive sync

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-sync.txt
export GDRIVE_CREDENTIALS=/path/to/service-account.json
python scripts/sync_drive.py --root /path/to/mounted/transcribe
```

The sync script is deliberately non-destructive: it reports queue state and creates missing local directories, but never deletes source audio.

## Optional Colab browser runner

`scripts/colab_runner.py` is an adapter for a **separately authenticated** Playwright/Chromium environment. Google authentication must be performed interactively on the runner and persisted in a local browser profile. Do not put cookies into GitHub, CI logs, or source control. Free Colab can change its UI and session policy, so this runner is best-effort rather than a guaranteed headless API.

```bash
pip install playwright
playwright install chromium
python scripts/colab_runner.py --notebook-url https://colab.research.google.com/github/JoTalbot/transcribe/blob/main/notebooks/transcribe_pipeline.ipynb --profile .auth/colab
```

The runner opens the notebook and attempts to invoke **Run all** using resilient UI selectors. If Google requests authentication, it pauses for interactive sign-in.

## Local validation

```bash
pip install -r requirements-dev.txt
python -m compileall scripts src tests
python -m json.tool notebooks/transcribe_pipeline.ipynb >/dev/null
python scripts/colab_exchange_worker.py --help
```

CI additionally validates the canonical notebook exchange contract and all script entrypoints.

## Notes

`faster-whisper` uses CTranslate2 and CUDA when available. Pyannote performs diarization separately; the notebook assigns each Whisper segment to the speaker with the greatest temporal overlap. This is intentionally simple, deterministic, and resumable. For highly overlapping speech, diarization-aware word-level alignment can be added later.

The dry-run exchange test validates transport, atomic file exchange, lease identity, result reconciliation, quarantine behavior, and retry semantics without GPU models. It does **not** prove actual Whisper, Pyannote, CUDA, or Colab inference. A real Colab GPU run with a small non-production recording remains the production validation gate.

Keep Colab sessions alive only through legitimate notebook/browser activity. The notebook includes a visible keep-alive snippet for users who choose to use it, but no method can guarantee a free Colab session indefinitely.
