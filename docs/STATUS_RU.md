# Статус проекта Transcribe

Дата проверки: 2026-09-15

## Текущее состояние

Проект находится на этапе доводки безопасного распределённого исполнения перед подключением реальных Oracle/Colab worker-процессов.

### Проверено и усилено

- PostgreSQL используется как каноническое состояние execution jobs.
- Захват задания защищён транзакционным lease-механизмом.
- Два конкурентных worker-процесса не должны получить одно и то же задание.
- `worker + lease_id` обязательны для heartbeat, completion и failure.
- Просроченный lease может быть переотдан другому worker.
- Старый worker не может завершить уже переотданное задание.
- Просроченный lease переводится в `retry`, а при достижении лимита попыток в `failed`.
- Integration tests покрывают heartbeat и предельное число попыток.
- PostgreSQL integration test покрывает полный обмен: dispatch → lease → reclaim → stale-result quarantine → принятие результата нового worker.
- Scheduler для DB-backed repository не может случайно перейти на небезопасный legacy recovery path из-за переданного тестового `now`.
- Colab worker не оставляет malformed claim в `processing`: такой request отправляется в quarantine.
- Worker tests соответствуют обязательному `worker + lease_id` протоколу.
- Exchange result application работает через канонический PostgreSQL repository и lease-aware `ExchangeCoordinator`, а не через новый пустой `InMemoryRepository`.
- Production bootstrap очереди больше не пишет `state/jobs.json`: `scripts/run_pipeline.py` создаёт recordings и stable stage jobs непосредственно в PostgreSQL.
- Добавлен отдельный `scripts/oracle_worker.py` как production entrypoint устойчивого Oracle-оркестратора: каждый цикл использует свежий PostgreSQL connection, применяет результаты, reclaim просроченных lease и dispatch через существующий `Scheduler`/`ExchangeCoordinator`.
- Oracle worker не использует legacy `JobStore`, поддерживает `--once`, периодический режим и корректное завершение по `SIGINT`/`SIGTERM`.
- Добавлены тесты управления циклом Oracle worker и проверки положительного интервала.
- README синхронизирован с новым Oracle daemon entrypoint.

## Последние исправления

1. Убрана зависимость integration tests от фиксированных задержек истечения lease. Ожидание reclaim/recovery выполняется через bounded polling с монотонным таймером. Временные PostgreSQL-соединения закрываются после проверок.
2. Добавлен PostgreSQL-backed E2E-тест coordinator/exchange: результат старого worker после reclaim не меняет состояние задания и перемещается в quarantine, а результат нового worker с актуальным `lease_id` успешно завершает задание.
3. Исправлен scheduler recovery bypass: lease-aware repository всегда использует транзакционный `recover_stale()`.
4. Исправлен Colab exchange worker: malformed claim после перемещения в `processing` гарантированно уходит в quarantine.
5. Исправлен production exchange submission: `scripts/submit_exchange_jobs.py` больше не создаёт exchange jobs напрямую из локального `JobStore`. Теперь он требует PostgreSQL, сверяет manifest paths с каноническими записями БД и выполняет dispatch через `Scheduler`/`ExchangeCoordinator` с lease ownership.
6. Исправлен production result application: `scripts/apply_exchange_results.py` больше не применяет результаты к эфемерному `InMemoryRepository`; теперь он требует `TRANSCRIBE_DATABASE_URL` или `--database-url` и применяет результаты через PostgreSQL lease ownership.
7. Исправлен production bootstrap: `scripts/run_pipeline.py` переведён на PostgreSQL canonical state, добавлена проверка конфликтующего `recording_id -> path`, а создание stage jobs стало идемпотентным через `SqlRepository.put_job`.
8. README синхронизирован с новым PostgreSQL-only queue bootstrap и убраны устаревшие аргументы `--jobs` из production-команды dispatch.
9. Добавлен Oracle scheduler daemon поверх уже проверенного lease-aware пути. Важное разделение сохранено: Oracle оркестрирует и выдаёт jobs, Colab выполняет GPU inference.

## CI

После изменений `scripts/oracle_worker.py`, тестов и README GitHub Actions должен завершить новый push-triggered запуск `Validate`. До получения фактического успешного результата нельзя объявлять проект CI-green.

## Следующий production gate

1. Получить успешный полный CI после добавления Oracle worker.
2. Если CI найдёт ошибку, исправить её в репозитории и повторить проверку.
3. Проверить реальный запуск Oracle daemon на ARM Ubuntu с PostgreSQL и exchange directory без production-аудио.
4. Проверить реальный Colab exchange worker на тестовом job и lease ownership.
5. Проверить, что оставшиеся вызовы `JobStore` ограничены legacy/local тестовой инфраструктурой и не участвуют в production orchestration.
6. Выполнить dry-run полного Oracle → exchange → Colab пути без пользовательского production-аудио.
7. Затем выполнить ограниченный production smoke test.

## Ограничение

Бесплатный Google Colab не предоставляет гарантированный headless/public API. Поэтому Colab остаётся best-effort GPU worker через предусмотренный exchange/runner механизм, а Oracle должен оставаться устойчивым оркестратором и источником истины состояния.
