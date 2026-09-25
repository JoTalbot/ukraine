# Ukraine — Production Readiness Report

**Дата:** 2026-09-25 (батч 2)  
**Репозиторий:** `JoTalbot/ukraine`  
**Аудит:** шаг 2 — обновление устаревших статусов CI-02/CHAIN-02 в ROADMAP на доказательствах git (решение владельца (е))

## Итог

**STATUS DOCS SYNCED: CI-02 и CHAIN-02 в ROADMAP приведены к фактическому состоянию HEAD. Control plane: GREEN (P1–P5 зелёный). Полный data product: NOT YET CERTIFIED.**

Устаревшие статусы (урок 14: «docs лагают коммиты») исправлены на доказательствах: коммиты фиксов `9477672` и `edd6516` в истории HEAD, порядок шагов workflow сверён текстом файла, P1 lint зелёный. Код не менялся.

## Шаги

### Шаг 1 — Доказательства (только чтение, свежие команды этой сессии)
- CI-02: `git log --oneline -- scripts/validate_release.py` → `9477672 fix(ci): satisfy Ruff in release validator` в истории (HEAD включает коммит); runtime — `ruff check --config ruff.toml scripts tests` = RC=0 (2026-09-25).
- CHAIN-02: `git show --stat edd6516` → «fix(ci): bind observability artifacts before validation», затронут `.github/workflows/release-observability.yml`; в HEAD порядок: строка 36 (evidence) → 38 (bind) → 40 (validate) — сверено с контролем `ukraine-data-ci.yml` (строки 44→46→48).
- Старые формулировки ROADMAP: CI-02 «implementation follows immediately», CHAIN-02 «…is the next runtime fix» — устарели (фиксы в HEAD).

### Шаг 2 — Правки (только патчер)
- `docs/ROADMAP.md`: 2 пункта (CI-02, CHAIN-02) заменены на «Implemented: …» с указанием коммитов и даты верификации; guard=1 на каждый новый блок.
- `docs/AGENT_CANON.md`: «ТОЧКА ВОЗОБНОВЛЕНИЯ» (снимок 2026-09-25, шаг 2); (е) в «ОТКРЫТЫХ РЕШЕНИЯХ» помечено реализованным; новый урок 20 (суффикс `-BATCH2` для второго отчёта дня).
- Тень: md5-паритет с копией канона в репо — два непустых равных хеша.

### Шаг 3 — Тесты после правки (все профили)
| Профиль | Результат |
|---|---|
| P1 lint | RC=0, «All checks passed!» |
| P2 compile | RC=0 |
| P3 тесты (полный) | 170 passed, 1 skipped (skipped = torch, штатно) |
| P4 контракт графа | 6 passed |
| P5 CI smoke-цепочка | RC=0 ×6, «Release contract OK» |

## Остаточные слабые места

1. Discovery bootstrap не завершён: next_batch=95 из 359, failed=42, blocked=53, successful=0, bootstrap_complete=false → NOT YET CERTIFIED.
2. Authoritative promotion authorization отсутствует → production намеренно RED / fail-closed.
3. Локальный прогон discovery в песочнице НЕ выполняется: state персистит CI по расписанию (гонка, урок 19) — только по явному решению владельца (в).
4. Охват шага — CI-02/CHAIN-02 (решение (е)); статусы прочих пунктов ROADMAP не пересматривались.

## Изменения

| Файл | Изменение |
|---|---|
| `docs/ROADMAP.md` | статусы CI-02, CHAIN-02 → «Implemented: …» (доказательства: `9477672`, `edd6516`, порядок workflow, P1) |
| `docs/AGENT_CANON.md` | «ТОЧКА ВОЗОБНОВЛЕНИЯ» (шаг 2), (е) реализовано, урок 20 |
| `docs/STATUS_REPORT_2026-09-25-BATCH2.md` | создан (данный отчёт) |

Код не менялся: `scripts/`, `tests/`, `schemas/`, `.github/` не тронуты.

## Решение

STEP 2 COMPLETE: ROADMAP synced to HEAD for CI-02/CHAIN-02 (git-verified).

Следующий рубеж — по решениям владельца: (в) discovery bootstrap (песочница или только расписание Actions — CI уже персистит state); (а) ротация origin-токена (состыл в чате 2026-09-22). Fail-closed политика не ослабляется.
