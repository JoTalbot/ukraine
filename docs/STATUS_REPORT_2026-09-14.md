# Ukraine — Production Readiness Report

**Дата:** 2026-09-14  
**Репозиторий:** `JoTalbot/ukraine`  
**Текущий hardening batch:** `96ae5c4774a3ab81a987e137921f329f4dc00408`

## Итог

**Control plane: GREEN по архитектуре и контрактам. Полный data product: NOT YET CERTIFIED.**

## Шаг 1 — Повторная проверка production readiness

Проверены readiness gate, hardening, artifact chain, promotion authorization, discovery state и последние GitHub Actions. Production остаётся **RED / fail-closed**.

Причина не в отсутствии проверок: authoritative production authorization отсутствует, а discovery bootstrap не завершён. Production Release Gate корректно отказывается продолжать без подтверждённого release control plane.

## Шаг 2 — Найденная security-слабость

`verify_promotion_authorization.py` принимал пути к production artifact и evaluation evidence без строгого ограничения рабочей директорией. Абсолютный путь или `..` мог привести к чтению файла вне репозитория.

## Шаг 3 — Исправление path safety

Verifier теперь принимает только относительные пути внутри `artifacts/`, запрещает абсолютные пути и компоненты `..`, а после `resolve()` дополнительно проверяет принадлежность корню репозитория.

Это fail-closed поведение: небезопасный путь блокирует authorization.

## Шаг 4 — Negative tests

Добавлены тесты для подмены production artifact, отсутствующей authorization, `../` path traversal, абсолютного пути и небезопасного evaluation evidence path.

## Шаг 5 — Discovery bootstrap

Текущее состояние всё ещё требует восстановления failed batches. Последнее зафиксированное состояние: `batch_count=360`, `failed_batches=0..20`, `bootstrap_complete=false`.

`completed_batches` не используется как доказательство успешного bootstrap без проверки `successful_batches` и отсутствия failures.

## Шаг 6 — Runtime

Последние проверки на HEAD `eca5f6344df434b00e08a8fd70f5e0335a742390` дали:

- Release Control Plane: **FAILURE**;
- Production Release Gate: **FAILURE**.

Gate остановился на проверке release control plane. Это соответствует fail-closed политике и не является основанием для создания фиктивной authorization.

## Шаг 7 — Оставшиеся слабые места и улучшения

### P0

1. Завершить discovery bootstrap: `successful_batches == batch_count`, `failed_batches == []`, `bootstrap_complete=true`.
2. Получить реальные production artifact и evaluation evidence.
3. Оформлять promotion authorization только для конкретного проверенного release.

### P1

4. Защитить authorization отдельной approval boundary: protected environment/branch или криптографическая подпись.
5. Добавить независимый signed provenance/attestation.
6. Добавить deployment-side atomic rollback с фактическим recovery test.
7. Сделать discovered-data workflow явно красным после сохранения progress, если batch содержит failed resources.

### P2

8. Расширить freshness/retry/recovery observability.
9. Добавить периодическую end-to-end production certification.

## Сертификационная матрица

| Контур | Статус |
|---|---|
| Production architecture | **GREEN** |
| Hardening contracts | **GREEN / УКРЕПЛЕНЫ** |
| Promotion path safety | **GREEN / ИСПРАВЛЕНО** |
| Cryptographic artifact chain | **УКРЕПЛЕНА** |
| Authoritative promotion authorization | **RED / ОТСУТСТВУЕТ** |
| Discovery bootstrap | **RED / НЕ ЗАВЕРШЁН** |
| Real producer evidence | **RED / НЕДОСТАТОЧНО** |
| Deployment rollback evidence | **RED / НЕДОСТАТОЧНО** |
| Full production certification | **RED / NOT YET CERTIFIED** |

## Решение

**PRODUCTION HARDENING IN PROGRESS. CONTROL-PLANE ARCHITECTURE GREEN. FULL DATA PRODUCT NOT YET CERTIFIED.**

Изменения verifier и тестов запушены в `main`. Следующий production-критичный рубеж — реальные успешные data producer/evaluation/release evidence и защищённое approval.
