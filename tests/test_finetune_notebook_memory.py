"""Guard against the Kaggle T4 OOM that killed ua-legal-lm-ft v17:
micro-batch must stay small with gradient accumulation, gradient
checkpointing enabled, and expandable CUDA segments configured."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NB = json.loads((ROOT / "training" / "kaggle" / "legal_lm_finetune.ipynb").read_text(encoding="utf-8"))
SRC = "\n".join("".join(c["source"]) for c in NB["cells"])


def test_micro_batch_is_small_and_accumulated():
    assert "CTX, BATCH, GRAD_ACCUM, STEPS, LR = 512, 2, 4, 2000, 1e-4" in SRC
    assert "(out.loss / GRAD_ACCUM).backward()" in SRC


def test_gradient_checkpointing_and_cache_off():
    assert "model.gradient_checkpointing_enable()" in SRC
    assert "model.enable_input_require_grads()" in SRC
    assert "model.config.use_cache = False" in SRC


def test_cuda_allocator_uses_expandable_segments():
    assert "PYTORCH_CUDA_ALLOC_CONF" in SRC
    assert "expandable_segments:True" in SRC


def test_grad_accum_propagated_to_training_subprocess():
    assert "GRAD_ACCUM=str(GRAD_ACCUM)" in SRC
    assert "GRAD_ACCUM = int(os.environ.get('GRAD_ACCUM', '4'))" in SRC
