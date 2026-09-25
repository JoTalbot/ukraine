# Ukraine — Production Readiness Report

**Дата:** 2026-09-25  
**Репозиторий:** `JoTalbot/ukraine`  
**Аудит:** этап 0 — восстановление среды + локальный CI-эквивалент (P1–P5) + пересчёт состояния

## Итог

**Control plane: GREEN (контракты, локальный CI-эквивалент P1–P5 зелёный). Полный data product: NOT YET CERTIFIED.**

Discovery bootstrap не завершён (next_batch=95 из 359; failed=42; successful=0), authoritative production authorization отсутствует — production намеренно RED / fail-closed. Фиктивного evidence и promotion authorization не создано. Ключей HF/Kaggle в песочнице нет — имитация публикаций и GPU-обучения запрещена и не выполнялась.

## Шаги

### Шаг 1 — Этап 0: восстановление среды
- Чистая песочница: репозитория не было → клон из origin по токену стартера (timeout 300), ветка `main`.
- HEAD на старте: `d56e1e559c5aeeca9a321b27548ec790cab2cbcd` — тождествен анонимному `git ls-remote` (зафиксированный в стартере `980f451…` устарел: пересчитан по правилу «или новее — пересчитать»).
- Сеть жива: `git ls-remote https://github.com/JoTalbot/ukraine.git HEAD` → 1 строка `<40-hex>\tHEAD`.
- Зависимости (устанавливаются каждой сессией по lock): ruff 0.16.5, pytest 9.1.1, pyarrow 25.0.1 — ровно значения канона.
- Права: 11 скриптов `scripts/*.py` возвращены в 755 (Этап 0.4, ДО lint); после — `git status --porcelain` = 0.
- `git fsck --full` = RC=0; диск: 20G свободно; интерпретатор `/usr/local/bin/python3` (3.13.14).

### Шаг 2 — Baseline P1–P5 (локальный эквивалент job `validate`)
| Профиль | Команда | Результат |
|---|---|---|
| P1 lint | `ruff check --config ruff.toml scripts tests` | RC=0, «All checks passed!» |
| P2 compile | `python3 -m compileall -q scripts tests` | RC=0 |
| P3 тесты (полный) | `python3 -m pytest tests/ -q` | 170 passed, 1 skipped (2.29s) |
| P4 контракт графа | `pytest tests/test_entity_graph_provenance.py -q` | 6 passed |
| P5 CI smoke-цепочка | 6 команд `ukraine-data-ci.yml` (validate) | RC=0 ×6, «Release contract OK» |

- 1 skipped в P3 — `tests/test_train_lm.py` (torch в песочнице отсутствует) — штатно (урок 16), не «сбой, который чинят».
- После P5: `rm -rf artifacts/status` — выполнено (ловушка 17).

### Шаг 3 — Пересчёт состояния (свежие команды этой сессии)
- Discovery (`.github/state/discovered-open-data-progress.json`): batch_count=359, next_batch=95, failed=42, blocked=53, successful=0, completed_batches=0, bootstrap_complete=false, last_batch=94, updated_at_utc=2026-09-24T23:20:13+00:00.
- Дельта от канона 2026-09-22: next_batch 80→95, failed 27→42 — CI продолжает персистить state (урок 19); «failed batches не маскируются под успешные».
- Замечание: в отчёте 2026-09-14 было batch_count=360, пересчёт сейчас = 359 (state перезаписывается CI-ранами; вмешательств не было).
- Доки: `docs/ROADMAP.md` = 98 строк; последний по имени STATUS_REPORT до этого отчёта — `docs/STATUS_REPORT_2026-09-14.md` (файлов от 2026-09-14 два).
- Интерпретатор 3.13.14 (песочница) vs 3.12 (CI) — расхождение штатное, зафиксировано (урок 15).

### Шаг 4 — Доки
- Обновлён раздел «ТОЧКА ВОЗОБНОВЛЕНИЯ» канона пересчитанными числами (снимок 2026-09-25).
- Тень `/home/user/work/ukraine-CANON.shadow.md`: md5-паритет с копией в репо — два непустых равных хеша.
- Отчёт создан патчером `/home/user/work/patch-step1-status-report.py` (страж идемпотентности, атомарная запись, сохранение режима).

## Остаточные слабые места

1. Discovery bootstrap не завершён: next_batch=95, failed=42, blocked=53, successful=0 → полный data product NOT YET CERTIFIED.
2. Authoritative promotion authorization отсутствует → production корректно RED / fail-closed.
3. Реального producer/evaluation evidence нет (ключей HF/Kaggle в песочнице нет — имитация запрещена).
4. Статусы CI-02/CHAIN-02 в ROADMAP могут быть устаревшими: коммиты фиксов `9477672` и `edd6516` в истории присутствуют (проверено `git cat-file` + `merge-base`), но текст ROADMAP до сих пор говорит о «next runtime fix» — обновление статусов = решение владельца (е); утверждение о статусе — только через `git log --oneline -- docs/ROADMAP.md`.
5. Токен стартера вставлен в чат → считать стользым (урок 18); ротация — за владельцем (решение (а)).

## Изменения

| Файл | Изменение |
|---|---|
| `docs/STATUS_REPORT_2026-09-25.md` | создан (данный отчёт) |
| `docs/AGENT_CANON.md` | обновлён раздел «ТОЧКА ВОЗОБНОВЛЕНИЯ» (пересчёт 2026-09-25) |

Код не менялся: `scripts/`, `tests/`, `schemas/`, `.github/` не тронуты.

## Решение

STEP 1 COMPLETE: environment restore + baseline P1-P5 GREEN + state recompute.

Следующий рабочий рубеж — по решениям владельца: (в) discovery bootstrap в песочнице или только в расписании GitHub Actions; (е) обновление устаревших статусов ROADMAP. Fail-closed политика не ослабляется.
