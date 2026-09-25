# Ukraine — Production Readiness Report

**Дата:** 2026-09-25 (батч 4)  
**Репозиторий:** `JoTalbot/ukraine`  
**Аудит:** шаг 4 — bootstrap в песочнице: батчи 98, 99, 100 прогнаны в `--dry-run` (батч 97 — CI)

## Итог

**Bootstrap в песочнице работает батчами: 98–100 прогнаны и персистнуты (логика workflow): next_batch=101, failed=47, blocked=54, successful=0. 80 ресурсов скачано и проверено SHA-256 (dry-run); 7 реальных отказов (403/404 у муниципальных сайтов + битый file:/// URL); 91 blocked (opendata.gov.ua — сломан, измерено повторно; data.gov.ua — троттлинг песочницы). Имитации success нет (урок 21). Production: RED / fail-closed намеренно (bootstrap_complete=false).**

## Шаги

### Шаг 1 — Этап 0 (ситуация (в) + дрейф)
- origin восстановлен по стартеру; identity; 11×755 (урок 13); пакеты дёрнулись снова (pytest 9.0.3) → переустановка по lock: ruff 0.16.5, pytest 9.1.1, pyarrow 25.0.1.
- CI запушил `2fbb5c7` (батч 97: failed=3, blocked=1; next_batch=98) → FF-pull; на старте работы локаль == origin.

### Шаг 2 — Свежий каталог + выбор батчей
- Каталог: 3585 датасетов (стабильно к шагу 3: 3585); CKAN API из песочницы жив (проба 0.8s).
- Выбор (алгоритм workflow): 98 → 99 → 100 последовательно.

### Шаг 3 — Прогон батчей (dry-run; артефакты в /home/user/work/)
| Батч | datasets | downloaded | failed | blocked | Итог по логике workflow |
|---|---|---|---|---|---|
| 98 | 10 | 20 | 5 | 0 | failed_batches (98): rada-uzhgorod 404; city-adm.lviv.ua 403 ×3; битый URL `file:///C:/Users/admin/…` (мусорная метаданные источника) |
| 99 | 10 | 60 | 2 | 83 | failed_batches (99): dniprorada 404 ×2; blocked: opendata.gov.ua (source_unavailable ×7) + data.gov.ua (source_throttled ×76: 429 → halt после 2 попаданий) |
| 100 | 10 | 0 | 0 | 8 | blocked_batches (100): opendata.gov.ua (TLS ReadTimeout 15.6s; хост сломан с 2026-09-14) |

- Инцидент (урок 22): батч 99 впервые прогнан на 0 датасетах — репо-каталог был уже восстановлен до HEAD (fallback из 500); повтор на свежем каталоге из `/home/user/work/` через `--catalog`. Вреду state нет (dry-run-страж: «чистый» прогон на 0 датасетах не персистится).

### Шаг 4 — Персист state (логика workflow, по батчам)
- Перед каждой записью — fetch + ff (новых коммитов CI за шаг не было); финал: next_batch=101, failed=47, blocked=54, successful=0, last_batch={100, bootstrap, failed=0, blocked=8}, unreachable_hosts=[opendata.gov.ua].
- Один state-коммит на батчи 98–100 (`chore(data): persist discovered open-data progress`) — песочница прогоняет несколько батчей за сессию; файл несёт накопленный state.

### Шаг 5 — Тесты после правок (все профили)
| Профиль | Результат |
|---|---|
| P1 lint | RC=0, «All checks passed!» |
| P2 compile | RC=0 |
| P3 тесты (полный) | 170 passed, 1 skipped (skipped = torch, штатно) |
| P4 контракт графа | 6 passed |
| P5 CI smoke-цепочка | RC=0 ×6, «Release contract OK» |

## Остаточные слабые места

1. `opendata.gov.ua` сломан (TLS-хендшейк висит) → 54 blocked-батча не разблокируются до возвращения источника; на нём значительная доля ресурсов каталога.
2. `data.gov.ua` троттлит раннер песочницы (429) → часть батча 99 заблокирована троттлингом; у CI (IP GitHub) лимит может не срабатывать.
3. Реальные отказы накапливаются (47 батчей в retry-очереди): 403/404 у муниципальных сайтов — проблема источников, не пайплайна.
4. successful=0: песочница не может дать successful (нет HF_TOKEN); публикацию делает CI.
5. next_batch=101 из 359 — bootstrap далёк от завершения.

## Изменения

| Файл | Изменение |
|---|---|
| `.github/state/discovered-open-data-progress.json` | батчи 98, 99 → failed; 100 → blocked; next_batch=101 |
| `docs/STATUS_REPORT_2026-09-25-BATCH4.md` | создан (данный отчёт) |
| `docs/AGENT_CANON.md` | «ТОЧКА ВОЗОБНОВЛЕНИЯ» (шаг 4), урок 22 (свежий каталог для sandbox-sync) |

Код не менялся: `scripts/`, `tests/`, `schemas/`, `.github/` не тронуты.

## Решение

STEP 4 COMPLETE: sandbox bootstrap — batches 98-100 run (dry-run), state persisted per project rules (next_batch=101, failed=47, blocked=54), no success emulation.

Дальше (песочница): батчи 101+ и/или retry-очередь failed (47). Зеркалирование 96–100 с публикацией — CI/владелец (workflow_dispatch, `batch_index=96…100`). Fail-closed не ослабляется.
