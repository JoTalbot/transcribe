# Production gate

Дата проверки: 2026-09-17

Текущий baseline `main`: `06e4db936592c98791e94ebd24315afa2d60dd68`.

Repository-side validation подтверждена для предыдущего функционального head `d3c52bb7d87f6126e57eede412c3514298bec63a`: `Validate #619` и `CI Smoke #527` завершились успешно. В этом head добавлен regression-тест на отказ удаления исходного request после успешного эксклюзивного Colab claim. Документация статуса синхронизирована с этим состоянием.

## Остаётся физически подтвердить

`Oracle → Google Drive → Colab CUDA → Whisper large-v3 → pyannote speaker-diarization-3.1 → SpeechBrain ECAPA → Google Drive → Oracle/PostgreSQL`

Нужно сохранить:

- wall-clock timings;
- model load time;
- RAM/VRAM;
- размеры и SHA-256 артефактов;
- повторный запуск без duplicate/corrupt outputs;
- interruption → lease expiry/reclaim → stale-result quarantine → успешное продолжение под новым lease;
- evidence snapshot через `scripts/colab_gpu_evidence.py`;
- физическую проверку поведения `O_CREAT | O_EXCL` именно на используемом Google Drive filesystem.

CI, unit/integration tests и dry-run не считаются доказательством физического GPU E2E. До получения этой evidence production gate остаётся открытым.
