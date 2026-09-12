# Transcribe: Whisper large-v3 + speaker diarization

Automated audio transcription with speaker diarization. Heavy inference runs in free Google Colab GPU; GitHub Actions validates the project and optional Drive sync reports the queue.

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
    +--> resumable state + stable jobs
    |
    +--> submit_exchange_jobs.py ---> Drive/exchange/jobs/*.json
                                      |
                                      v
                               Colab GPU worker
                               Whisper + Pyannote
                                      |
                                      v
                               output + manifests
                                      |
                                      v
                               exchange/results/*.json
```

The manifest path is the source of truth for locating audio. A `recording_id` is derived from the relative path, so the worker must not assume that the ID is the original filename. Exchange envelopes therefore carry the exact `input_path`.

The orchestration layer keeps the logical stages resumable and idempotent. The current Colab inference adapter performs the GPU-heavy ASR/diarization operation; the broader 24-stage intelligence roadmap remains a target architecture rather than a claim that every stage is already implemented.

### 5-minute setup

1. Accept the model terms for `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0` on Hugging Face.
2. Create a Hugging Face access token with read access. In Colab open **Secrets**, create `HUGGINGFACE_TOKEN`, and allow notebook access.
3. Put audio into `MyDrive/transcribe/input`. The notebook creates `output` and `state` automatically.
4. Open `notebooks/transcribe_pipeline.ipynb` in Colab and use **Runtime -> Run all**.
5. Results are written as `.txt`, `.json`, and `.srt` under `MyDrive/transcribe/output`.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/JoTalbot/transcribe/blob/main/notebooks/transcribe_pipeline.ipynb)

## GitHub Actions secrets

For optional server-side Drive queue checks, add `GDRIVE_CREDENTIALS` containing a Google service-account JSON. Share the Drive `transcribe` folder with that service-account email. Do **not** commit credentials or Google cookies.

`HUGGINGFACE_TOKEN` is only needed by Colab and should normally live in Colab Secrets, not GitHub Actions.

## Exchange queue

After building a manifest and creating local execution jobs, materialize those jobs for the Colab worker with:

```bash
python scripts/submit_exchange_jobs.py \
  --manifest state/manifest.json \
  --jobs state/jobs.json \
  --exchange /path/to/transcribe/exchange
```

The command reads `recording_id -> path` from the manifest and writes an exchange `JobEnvelope` containing the exact relative `input_path`. It skips jobs that are already running or completed, so repeated submission is safe.

The Colab exchange worker watches `exchange/jobs`, claims requests into `processing`, runs GPU inference, writes `exchange/results`, and removes the processing marker after completion or failure.

## Outputs

For `example.wav`, the pipeline produces:

- `example.txt`: `[00:01:23 - SPEAKER_00]: text`
- `example.json`: source metadata, diarization segments and transcript segments
- `example.srt`: speaker-labelled subtitles
- `state/processed.json`: resumable processing registry

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
python -m compileall scripts
python -m json.tool notebooks/transcribe_pipeline.ipynb >/dev/null
```

## Notes

`faster-whisper` uses CTranslate2 and CUDA when available. Pyannote performs diarization separately; the notebook assigns each Whisper segment to the speaker with the greatest temporal overlap. This is intentionally simple, deterministic, and resumable. For highly overlapping speech, diarization-aware word-level alignment can be added later.

Keep Colab sessions alive only through legitimate notebook/browser activity. The notebook includes a visible keep-alive snippet for users who choose to use it, but no method can guarantee a free Colab session indefinitely.
