# Ukraine — Production Readiness Batch 2

**Дата:** 2026-09-14

## Итог

**Control plane: GREEN по архитектуре. Full data product: NOT YET CERTIFIED.**

Production остаётся **RED / fail-closed**: discovery bootstrap не завершён, реальные production artifact/evaluation evidence отсутствуют в достаточном объёме, authoritative production authorization для проверенного release не оформлена.

## Шаг 1 — Readiness gate

Усилен `scripts/check_production_readiness.py`:

- `status-index.overall_state` теперь обязан быть `green`;
- сохраняется проверка полного набора сигналов и freshness policy;
- readiness напрямую вызывает `verify_promotion_authorization`;
- promotion считается зелёным только при реальной проверке artifact/evaluation файлов и их SHA-256.

## Шаг 2 — Regression tests

`tests/test_production_readiness.py` обновлён под реальный verifier:

- fixture создаёт реальные `artifacts/model.bin` и `artifacts/evaluation.json`;
- SHA-256 вычисляются из фактического содержимого;
- authorization содержит безопасные `artifact_path` и `evaluation_evidence_path`;
- добавлен тест: полный набор сигналов при `overall_state=red` не проходит readiness.

## Шаг 3 — Release Control Plane

`.github/workflows/release-control-plane.yml` усилен диагностикой:

- после aggregate + hardening evidence создаётся `release-control-plane-pre-gate`;
- snapshot сохраняется **до** promotion authorization;
- финальный `release-control-plane` загружается через `if: always()`.

Следствие: fail-closed отказ больше не уничтожает диагностическую картину запуска.

## Шаг 4 — Discovery

Текущее состояние остаётся:

- `batch_count=360`;
- `failed_batches=0..20`;
- `successful_batches=[]`;
- `completed_batches=0`;
- `bootstrap_complete=false`.

Failed batches не маскируются под успешные.

## Шаг 5 — Последний runtime результат

Наблюдаемый `Production Release Gate` run `34817788775` завершился `failure` на шаге `Verify release control plane result`. Это соответствует fail-closed модели при отсутствии валидного production control-plane результата и не является основанием объявлять production готовым.

## Остаточные слабые места

### P0

1. Завершить discovery bootstrap без подмены failed batches на success.
2. Получить реальные production artifact и evaluation evidence.
3. Выпустить authoritative authorization только для конкретного проверенного release.

### P1

4. Защитить approval отдельной boundary: protected environment/branch или подпись.
5. Добавить signed provenance/attestation.
6. Реализовать deployment-side atomic rollback и фактический recovery test.
7. Зафиксировать фактический CI результат после текущих изменений.

### P2

8. Усилить freshness/retry/recovery observability.
9. Добавить периодическую end-to-end certification.
10. Аудировать документацию, чтобы примеры READY/GREEN не выдавались за текущую сертификацию.

## Изменения

- `b7def824eb84e7cfd33e4b191be6620d307b4a12` — control-plane overall state стал обязательным условием readiness.
- `724abac54afb6629ab200882a2a5223952d2a5da` — readiness tests привязаны к реальным artifact/evaluation fixtures и SHA-256.
- `0a4c0b3c209044a2dd0d1fcedce6992c3fdc9ed0` — добавлен pre-gate diagnostic snapshot и always-upload финального snapshot.

## Решение

**PRODUCTION HARDENING IN PROGRESS. FULL PRODUCTION CERTIFICATION: RED / NOT YET CERTIFIED.**

Production должен оставаться заблокированным до появления реальных producer/evaluation/release evidence, защищённого approval и доказанного deployment/rollback recovery.
