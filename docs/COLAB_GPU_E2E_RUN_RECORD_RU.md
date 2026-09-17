# Transcribe: журнал физического Colab GPU E2E

Этот файл предназначен только для фактических запусков. CI, dry-run и ручная проверка кода не являются физическим GPU evidence.

## Run metadata

- Run ID:
- Date/time UTC:
- Oracle commit SHA:
- Colab notebook revision:
- Input audio identifier:
- Input audio SHA-256:
- Colab runtime type:
- GPU model:
- GPU VRAM:
- CUDA version:
- PyTorch version:

## Pipeline result

| Stage | Worker | Status | Artifact ID | Size | SHA-256 | Duration s |
|---|---|---|---|---:|---|---:|
| ingest | Oracle | | | | | |
| normalize | Oracle | | | | | |
| asr | Colab GPU | | | | | |
| diarization | Colab GPU | | | | | |
| embeddings | Colab GPU | | | | | |
| text_analysis | Oracle | | | | | |
| topics | Oracle | | | | | |
| linking | Oracle | | | | | |
| graph | Oracle | | | | | |

## Runtime measurements

- Total E2E wall-clock:
- Whisper model load:
- pyannote model load:
- ECAPA model load:
- Peak process RSS:
- Peak GPU memory allocated:
- Peak GPU memory reserved:

## Integrity checks

- [ ] All 9 jobs completed.
- [ ] Every artifact manifest verified.
- [ ] No duplicate artifact IDs.
- [ ] No checksum/size mismatch.
- [ ] No result entered quarantine during the normal run.
- [ ] Results were applied by Oracle and removed from `results/`.
- [ ] PostgreSQL contains final artifact IDs and completed recording status.

## Deterministic repeat

- Repeat Run ID:
- [ ] Same logical artifact identities were reused where the contract requires identity stability.
- [ ] No corrupt or conflicting duplicate publication occurred.
- [ ] All manifests and payloads passed the artifact audit.

## Lease interruption / reclaim

- Interrupted job:
- Original worker:
- Original lease ID:
- Reclaimed worker:
- New lease ID:
- [ ] Original lease expired/reclaimed.
- [ ] Old worker result was rejected or quarantined.
- [ ] New lease completed successfully.
- [ ] Final PostgreSQL state belongs to the new lease.
- [ ] No stale result overwrote the final artifact/result.

## Evidence files

- `colab_gpu_evidence.json`:
- Worker metrics snapshot:
- Artifact audit JSON:
- Logs / screenshots:

## Acceptance

This record may be marked complete only after the evidence files above are attached to the project history and independently checked against the physical run. Empty fields are not evidence.
