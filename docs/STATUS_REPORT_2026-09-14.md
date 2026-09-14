# Ukraine — Production Readiness Report

**Дата:** 2026-09-14  
**Репозиторий:** `JoTalbot/ukraine`  
**Последний hardening batch:** `2d2087046ebf314a00279e3db44926c4071c5122`

## Итог

**Control plane: GREEN по архитектуре и контрактам. Полный data product: NOT YET CERTIFIED.**

## Шаг 1 — Production readiness audit

Проверены readiness, hardening, artifact chain и production workflows. Найдена слабость: READY-01 мог считать `PROM-01` зелёным по promotion event из deterministic self-test fixture. Это не является доказательством реального разрешения production-релиза.

## Шаг 2 — Исправление authoritative promotion gate

READY-01 теперь требует отдельный `artifacts/status/production-promotion-authorization.json`.

Авторизация должна содержать точный `source_commit`, `model_id`, SHA-256 production artifact и evaluation evidence, `approval_identity`, положительный `release_sequence` и `approved_at`.

Fixture из `production_hardening.py evidence` больше не может удовлетворить production authorization gate.

## Шаг 3 — Cryptographic chain

CHAIN-01 теперь включает promotion authorization в SHA-256 binding. Отсутствие, изменение или несоответствие authorization делает chain красной.

## Шаг 4 — Tests

Добавлен negative test: отсутствие authoritative authorization обязано давать READY-01 = RED. Существующая проверка порядка workflow сохраняет требование `hardening → chain → readiness`.

## Шаг 5 — Runtime verification

На commit `e344a79f9deb867f90fa951467ce9c09bcf1ad62` Production Release Gate ранее успешно завершился, но после нового исправления ожидаемое поведение изменилось: без реальной promotion authorization production gate должен быть RED. Это корректный fail-closed результат, а не регрессия.

## Текущий verdict

| Контур | Статус |
|---|---|
| Production architecture | **GREEN** |
| Hardening contracts | **GREEN / УКРЕПЛЕНЫ** |
| Cryptographic artifact chain | **УКРЕПЛЕНА** |
| Authoritative promotion authorization | **ТРЕБУЕТСЯ** |
| CI integration | **ОБНОВЛЕНО** |
| Discovery bootstrap | **НЕ ЗАКРЫТ** |
| Full production certification | **RED / NOT YET CERTIFIED** |

## Оставшиеся P0/P1 задачи

1. Проверить новый CI → Control Plane → Production Gate после текущих изменений.
2. Подтвердить, что отсутствие authorization действительно блокирует production.
3. После review сформировать authorization только для конкретного реального release artifact.
4. Завершить failed discovery batches и получить `bootstrap_complete=true`.
5. Проверить реальный EDRSR/Hugging Face producer run.
6. Подключить deployment-side atomic switch для фактического rollback.
7. Привязать реальный evaluation artifact к authorization и promotion event.
8. Провести финальную production certification.

## Решение

**Сейчас: PRODUCTION HARDENING IN PROGRESS / CONTROL-PLANE ARCHITECTURE GREEN.**

**Полный data product: NOT YET CERTIFIED.**

Главная найденная архитектурная слабость устранена: self-test больше не может притворяться реальным production approval. Теперь система лучше делает то, что от неё требуется: сомневается в человеке, артефакте и даже самой себе, пока не увидит доказательство.
