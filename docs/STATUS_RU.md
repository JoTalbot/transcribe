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
- Oracle worker теперь переживает временные ошибки dispatch/БД: ошибка одного цикла логируется, после чего daemon продолжает работу с обычным интервалом.
- Добавлены тесты управления циклом Oracle worker, проверки положительного интервала и восстановления после временной ошибки цикла.
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
10. Усилен Oracle daemon: единичный временный сбой PostgreSQL/exchange больше не завершает постоянный worker-процесс; добавлен regression test на повтор цикла после исключения.
11. Исправлен PostgreSQL exchange integration test: истечение lease теперь задаётся непосредственно через `NOW() - INTERVAL '1 second'`, поэтому тест не зависит от фактической длительности coordinator lease и выполняется детерминированно.

## CI

- `Validate #322` для коммита `6c7ca1ff` завершён успешно.
- `CI Smoke #223` для коммита `6c7ca1ff` завершён успешно.
- Полный Validate прошёл compile, notebook/schema validation, lint, весь pytest-набор, проверки script entrypoints и repository structure.
- Последний CI-green commit: `6c7ca1ff9b304e78c3a99b2354bd38eb37a41700`.

## Следующий production gate

1. Проверить реальный запуск Oracle daemon на ARM Ubuntu с PostgreSQL и exchange directory без production-аудио.
2. Проверить реальный Colab exchange worker на тестовом job и lease ownership.
3. Проверить, что оставшиеся вызовы `JobStore` ограничены legacy/local тестовой инфраструктурой и не участвуют в production orchestration.
4. Выполнить dry-run полного Oracle → exchange → Colab пути без пользовательского production-аудио.
5. Затем выполнить ограниченный production smoke test.

## Ограничение

Бесплатный Google Colab не предоставляет гарантированный headless/public API. Поэтому Colab остаётся best-effort GPU worker через предусмотренный exchange/runner механизм, а Oracle должен оставаться устойчивым оркестратором и источником истины состояния.
