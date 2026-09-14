# Ukraine — Production Readiness Report

**Дата:** 2026-09-14  
**Репозиторий:** `JoTalbot/ukraine`  
**Аудит:** production readiness / fail-closed release control

## Итог

**Control plane: GREEN по архитектуре и контрактам. Полный data product: NOT YET CERTIFIED.**

Production намеренно остаётся **RED / fail-closed**. Discovery bootstrap не завершён, authoritative production authorization отсутствует, а production gate корректно блокирует выпуск при красном control-plane результате.

## Шаг 1 — Текущее discovery-состояние

После предыдущей проверки scheduler реально обработал batch `22` и сохранил результат в `main`.

Текущее состояние:

- `batch_count=360`;
- `failed_batches=0..22`;
- `successful_batches=[]`;
- `completed_batches=0`;
- `next_batch=23`;
- `bootstrap_complete=false`;
- `updated_at_utc=2026-09-14T15:21:53.997478+00:00`.

Commit `6d471b5b2ad3fe16a9773dc6190f8e35611546f0` подтверждает переход `next_batch: 22 → 23` и добавление batch `22` в `failed_batches`. Это runtime-подтверждение liveness: наличие failed batches больше не блокирует переход к следующему ещё не проверенному batch. fileciteturn337file0 fileciteturn348file0

## Шаг 2 — Discovery scheduler

Scheduler сохраняет fail-closed семантику:

1. сначала выбирается batch, который ещё не был ни успешным, ни failed;
2. только после исчерпания непроверенных batch начинается retry failed batches;
3. failure batch сначала сохраняется в progress;
4. после сохранения job получает failure;
5. publication signal остаётся RED.

Это предотвращает starvation и одновременно исключает ложное объявление неполных данных успешными.

## Шаг 3 — Retry/backoff

В `scripts/data_gov_ua_discovered_sync.py` фактически присутствует усиленный retry-контур:

- HTTP `408`, `425`, `429` и все `5xx` retryable;
- числовой `Retry-After` учитывается;
- HTTP-date формат `Retry-After` разбирается через стандартный parser;
- задержка ограничивается `DATA_GOV_MAX_RETRY_WAIT`;
- при отсутствии корректного server hint используется exponential backoff;
- частичный файл удаляется перед повторной попыткой;
- после исчерпания попыток ресурс остаётся failed.

Regression test проверяет HTTP-date детерминированно, поэтому тест действительно проверяет parsing, а не случайно проходит на exponential fallback.

## Шаг 4 — CI / Release Gate

Новый production control-plane запуск `34861715866` завершился `failure` на ожидаемом gate: `Verify release control plane result`. Предыдущий aggregate run `34859951191` также прошёл все подготовительные стадии, включая manifest, producer signal, SBOM, status index и runtime hardening, но остановился на отсутствии authoritative promotion authorization. Следующие production-readiness шаги были корректно пропущены. 

Таким образом, текущий RED не является обходом или случайным падением тестов: release control намеренно блокирует production, пока нет полного проверенного release evidence и authorization.

## Шаг 5 — Production authorization

`artifacts/status/production-promotion-authorization.json` не должен создаваться фиктивно. Для разрешения production необходимы реальные:

- source/release commit;
- model/artifact identity;
- SHA-256 artifact;
- SHA-256 evaluation evidence;
- approval identity;
- положительный immutable release sequence;
- UTC approval timestamp.

До появления такого authoritative authorization production должен оставаться RED.

## Шаг 6 — Остаточные P0

1. Продолжить discovery bootstrap с batch `23+`.
2. После полного прохода выполнить retry failed batches и добиться `successful_batches == batch_count` и `failed_batches == []`.
3. Получить реальные producer/evaluation/release evidence.
4. Только затем сформировать и проверить authoritative promotion authorization.

## Шаг 7 — P1 hardening

- защищённая approval boundary: protected environment/branch или криптографическая подпись;
- независимый signed provenance/attestation;
- deployment-side atomic rollback;
- фактический recovery test;
- end-to-end regression после readiness verifier binding;
- расширенная observability для freshness/retry/recovery.

## Сертификационная матрица

| Контур | Статус |
|---|---|
| Production architecture | **GREEN** |
| Hardening contracts | **GREEN** |
| Promotion path safety | **GREEN** |
| Readiness → real artifact binding | **GREEN** |
| Discovery publication truthfulness | **GREEN** |
| Discovery progress persistence | **GREEN / RUNTIME** |
| Discovery scheduler liveness | **GREEN / RUNTIME** |
| Rate-limit/timeout retry policy | **GREEN / TESTED** |
| CI syntax/lint/test validation | **GREEN по последнему технически проверенному CI** |
| Cryptographic artifact chain | **УКРЕПЛЕНА, signed provenance отсутствует** |
| Authoritative promotion authorization | **RED / ОТСУТСТВУЕТ** |
| Discovery bootstrap | **RED / 23 из 360 ещё не начаты после первых 23 failed** |
| Real producer/evaluation evidence | **RED / НЕДОСТАТОЧНО** |
| Deployment rollback evidence | **RED / НЕДОСТАТОЧНО** |
| Full production certification | **RED / NOT YET CERTIFIED** |

## Решение

**PRODUCTION HARDENING IN PROGRESS. CONTROL-PLANE ARCHITECTURE GREEN. FULL DATA PRODUCT NOT YET CERTIFIED.**

Следующий рабочий рубеж — batch `23+`, затем полный retry-проход failed batches. Fail-closed политика не ослабляется. Production promotion не выполняется без реального release evidence и authoritative approval.
