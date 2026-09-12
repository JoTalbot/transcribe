# Stage contracts: ASR and diarization

The Colab GPU worker treats ASR and diarization as separate resumable stages.

## ASR

Input: source audio.

Outputs:
- `transcript.json` (`stage=asr`)
- `transcript.txt` (`stage=asr`)

## Diarization

Inputs:
- source audio
- ASR `transcript.json`

Outputs:
- `diarized.json` (`stage=diarization`)
- `diarized.txt` (`stage=diarization`)
- `diarized.srt` (`stage=diarization`)

Diarization never creates an ASR artifact. This preserves idempotency and makes retries/reprocessing stage-local.

The real-world identity of a person is never inferred from a `SPEAKER_XX` label alone.
