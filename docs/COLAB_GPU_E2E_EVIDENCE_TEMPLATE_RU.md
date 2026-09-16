# Transcribe: шаблон доказательств реального Colab GPU E2E

Этот документ заполняется **только фактическими данными физического запуска**. GitHub CI, dry-run и статический анализ сюда не считаются доказательством GPU-инференса.

## 1. Идентификация запуска

- Дата/время начала:
- Дата/время окончания:
- Git commit:
- Test recording ID:
- Exchange root:
- Oracle host/worker:
- Colab notebook/session:
- Run identifier:

## 2. Colab GPU

- GPU model:
- VRAM total:
- CUDA version:
- PyTorch version:
- `torch.cuda.is_available()`:
- Peak VRAM usage:
- Peak system RAM:

## 3. Model versions

- Whisper: `large-v3`
- Whisper backend/version:
- pyannote: `speaker-diarization-3.1`
- pyannote package version:
- SpeechBrain ECAPA model/version:
- Transformers/torchaudio versions:

## 4. Timing

| Operation | Start | End | Duration |
|---|---|---|---|
| Oracle ingest | | | |
| Oracle normalize | | | |
| Whisper model load | | | |
| pyannote model load | | | |
| ECAPA model load | | | |
| ASR | | | |
| diarization | | | |
| embeddings | | | |
| Oracle post-processing | | | |
| Full E2E | | | |

## 5. Artifact evidence

| Stage | Artifact ID | Kind | Size bytes | SHA-256 | Verified |
|---|---|---|---:|---|---|
| ingest | | `source_audio` | | | |
| normalize | | `audio` | | | |
| asr | | `json` | | | |
| diarization | | `json` | | | |
| embeddings | | `json` | | | |
| text_analysis | | | | | |
| topics | | | | | |
| linking | | | | | |
| graph | | | | | |

## 6. Pipeline acceptance

- [ ] `ingest` completed
- [ ] `normalize` completed
- [ ] `asr` completed with Whisper `large-v3`
- [ ] `diarization` completed with pyannote `speaker-diarization-3.1`
- [ ] `embeddings` completed with SpeechBrain ECAPA
- [ ] `text_analysis` completed
- [ ] `topics` completed
- [ ] `linking` completed
- [ ] `graph` completed
- [ ] No result entered `results/quarantine`
- [ ] Applied result was removed from `results/`
- [ ] PostgreSQL contains final artifact IDs and completed status

## 7. Repeat-run evidence

Second run date/time:

- Second run identifier:
- Same recording reused:
- Duplicate artifact IDs observed:
- Corrupt/tampered artifacts observed:
- Unexpected result files observed:
- Artifact checksum verification passed:
- Notes:

## 8. Interruption / reclaim evidence

- Worker interrupted during GPU job:
- Original worker ID:
- Original lease ID:
- Lease expiry observed:
- Oracle reclaim observed:
- New worker ID:
- New lease ID:
- Old result quarantined:
- New lease result accepted:
- Final job status:
- Notes:

## 9. Raw evidence references

Record links or paths to the actual evidence instead of pasting secrets:

- Colab execution output:
- Oracle worker log:
- PostgreSQL execution/job record:
- Exchange request:
- Exchange result:
- Artifact manifests:
- GPU metrics:
- Repeat-run evidence:
- Recovery evidence:

**Не записывать сюда `HUGGINGFACE_TOKEN`, API keys, cookies или другие секреты.**

## 10. Final acceptance

- [ ] Physical Oracle → Drive → Colab CUDA → Oracle route completed.
- [ ] Real GPU inference completed for all three GPU stages.
- [ ] All nine stages completed.
- [ ] Repeat run completed.
- [ ] Interruption/reclaim test completed.
- [ ] Evidence is sufficient to audit the run independently.

**Статус:** `UNVERIFIED | PASSED | FAILED`

**Комментарий:**
