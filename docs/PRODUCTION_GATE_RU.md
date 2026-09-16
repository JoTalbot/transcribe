# Production gate

Дата проверки: 2026-09-16

Текущий baseline `main`: `e3603ac60106295312b5176c80a5a8828a978e64`.

Repository-side validation подтверждена: `Validate #546` на baseline завершился успешно. Colab notebook теперь устанавливает GPU-зависимости до импорта `torch`.

## Остаётся физически подтвердить

`Oracle → Google Drive → Colab CUDA → Whisper large-v3 → pyannote speaker-diarization-3.1 → SpeechBrain ECAPA → Google Drive → Oracle/PostgreSQL`

Нужно сохранить:

- wall-clock timings;
- model load time;
- RAM/VRAM;
- размеры и SHA-256 артефактов;
- повторный запуск без duplicate/corrupt outputs;
- interruption → lease expiry/reclaim → stale-result quarantine → успешное продолжение под новым lease;
- evidence snapshot через `scripts/colab_gpu_evidence.py`.

CI и dry-run не считаются доказательством физического GPU E2E. До получения этой evidence production gate остаётся открытым.
