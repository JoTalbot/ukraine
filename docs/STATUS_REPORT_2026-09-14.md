# Ukraine — Production Readiness Report

**Дата:** 2026-09-14  
**Репозиторий:** `JoTalbot/ukraine`  
**Аудит:** production readiness / fail-closed release control

## Итог

**Control plane: GREEN по архитектуре и контрактам. Полный data product: NOT YET CERTIFIED.**

Production намеренно остаётся **RED / fail-closed**: discovery bootstrap не завершён, реального production artifact/evaluation evidence недостаточно, а authoritative production authorization не оформлена для конкретного проверенного release.

## Шаг 1 — Повторная проверка production readiness

Проверены readiness gate, hardening, artifact chain, promotion authorization, discovery state, workflow order и последние runtime-состояния. Контракты не позволяют превратить неполный release в production только наличием локальных/fixture-доказательств.

## Шаг 2 — Security path safety

`verify_promotion_authorization.py` ограничивает artifact/evaluation paths директорией `artifacts/`, запрещает абсолютные пути и `..`, а после `resolve()` проверяет принадлежность корню репозитория. Добавленные negative tests покрывают tamper, missing authorization и path traversal.

## Шаг 3 — Исправление publication truthfulness

В `.github/workflows/discovered-open-data-huggingface.yml` добавлен отдельный fail-шаг **после сохранения progress** и до записи publication signal. Если batch содержит failed resources, progress сначала сохраняется, затем job получает `failure`, поэтому `always()` publication signal фиксирует **RED**, а не ложный GREEN.

Это устраняет важный semantic gap между `continue-on-error` у mirror-шага и итоговым статусом producer workflow.

## Шаг 4 — Регрессионный тест workflow

В `tests/test_production_readiness.py` добавлена статическая проверка порядка:

`Persist bootstrap progress` → `Fail batch after persisting failure state` → `Write publication status signal`.

Также проверяется наличие `exit 1` и условия failure по `has_failures=true`.

## Шаг 5 — Нормализация discovery state

Состояние bootstrap приведено к однозначному виду:

- `batch_count=360`;
- `failed_batches=0..20`;
- `successful_batches=[]`;
- `completed_batches=0`;
- `bootstrap_complete=false`.

Ранее `completed_batches=21` конфликтовал с отсутствующим списком успешных batches. Теперь state честно отражает фактическое отсутствие подтверждённых успешных batch-результатов. Никакие failed batches искусственно успешными не объявлялись.

## Шаг 6 — Остаточные production-слабости

### P0

1. Завершить discovery bootstrap: `successful_batches == batch_count`, `failed_batches == []`, `bootstrap_complete=true`.
2. Получить реальные production artifact и evaluation evidence.
3. Оформить authoritative promotion authorization только для конкретного проверенного release.

### P1

4. Защитить authorization отдельной approval boundary: protected environment/branch или криптографическая подпись.
5. Добавить независимый signed provenance/attestation, а не только self-generated manifest.
6. Добавить deployment-side atomic rollback и фактический recovery test.

### P2

7. Расширить freshness/retry/recovery observability.
8. Добавить периодическую end-to-end production certification.

## Сертификационная матрица

| Контур | Статус |
|---|---|
| Production architecture | **GREEN** |
| Hardening contracts | **GREEN / УКРЕПЛЕНЫ** |
| Promotion path safety | **GREEN / ИСПРАВЛЕНО** |
| Discovery publication truthfulness | **GREEN / УКРЕПЛЕНО** |
| Cryptographic artifact chain | **УКРЕПЛЕНА, НЕ SIGNED PROVENANCE** |
| Authoritative promotion authorization | **RED / ОТСУТСТВУЕТ** |
| Discovery bootstrap | **RED / НЕ ЗАВЕРШЁН** |
| Real producer evidence | **RED / НЕДОСТАТОЧНО** |
| Deployment rollback evidence | **RED / НЕДОСТАТОЧНО** |
| Full production certification | **RED / NOT YET CERTIFIED** |

## Изменения этого батча

1. `ddf999d007b14e1c300f480599f0c322fc0a06b9` — workflow теперь краснеет после сохранения failed batch state.
2. `b330fc3ca5b26792be1b4445008711627536ef9e` — добавлен regression test для этого контракта.
3. `11afc0b5db2a044f832c28db183be883d997ec4f` — нормализован discovery progress state.

## Решение

**PRODUCTION HARDENING IN PROGRESS. CONTROL-PLANE ARCHITECTURE GREEN. FULL DATA PRODUCT NOT YET CERTIFIED.**

Следующий production-критичный рубеж не требует новых фиктивных зелёных файлов: нужны реальные успешные producer/evaluation/release evidence, после чего только конкретный release должен пройти защищённое approval и deployment/rollback verification.
