# Kaggle GPU training

Репродюцируемый переход GPU-обучения из GitHub Actions в Kaggle.

## Pipeline

1. GitHub Actions проверяет секрет `KAGGLE_API` и пушит кернел `training/kaggle/legal_lm_gpu.ipynb` в Kaggle (`kaggle kernels push`, GPU включён).
2. Кернел сам скачивает публичные Parquet-части `JoTalbot/ua-edrsr`, `edr/UO.zip` и `vat_payers/pdv.csv` из `JoTalbot/ua-open-data`, строит корпус (`scripts/build_lm_corpus.py`) и обучает GPT (`scripts/train_lm.py --device cuda`, dim 512 / layers 8 / ctx 384, ~29M параметров).
3. Метрики и сэмплы — в логе кернела; модель публикуется в HF Hub (`JoTalbot/ua-legal-lm`), если в Kaggle добавлен секрет `HF_TOKEN`.

## Секреты

- GitHub: `KAGGLE_API` — содержимое kaggle.json (JSON), только как Actions secret.
- Kaggle (Attachments → Secrets): `HF_TOKEN` — токен Hugging Face с правом write, ПУБЛИКОВАТЬ МОДЕЛЬ.

Секреты никогда не коммитятся и не печатаются в логах.

## Ограничения Kaggle

- GPU-квота ~30 ч/неделю; включённый интернет в кернеле обязателен (скачивание данных).
- Для `kaggle kernels push` аккаунт должен быть верифицирован (телефон). Иначе push упадёт с предупреждением в логе workflow.
- Ручной запуск: вкладка Notebooks в Kaggle → New Notebook → прикрепить `legal_lm_gpu.ipynb` → Settings: GPU T4, Internet on.

## Параметры по умолчанию (в первой ячейке ноутбука)

| Параметр | Значение |
|---|---|
| YEARS | 2020–2026, по 8 Parquet-частей на год (≈14M строк до лимита) |
| EDRSR_LIMIT / EDR_LIMIT / VAT_LIMIT | 3M / 2M / 400k строк |
| DIM / LAYERS / CTX / BATCH / STEPS | 512 / 8 / 384 / 16 / 6000 (~1.5–2.5 ч на T4) |

## Приватность

Тільки законно опубліковані відкриті дані; знеособлення джерела зберігається (`no_deanonymization`).
