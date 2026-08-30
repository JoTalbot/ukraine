"""Smoke test: the LM trainer runs end to end on a toy corpus (CPU, seconds)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import importlib.util

spec = importlib.util.spec_from_file_location("train_lm", Path(__file__).resolve().parents[1] / "scripts" / "train_lm.py")
train_lm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(train_lm)

import torch

TOY = ("Суд: Шостий апеляційний суд. Справа № 500/1540/26. Категорія: Крадіжка. Суддя: Шевченко І. М.\n"
       "ТОВАРИСТВО З ОБМЕЖЕНОЮ ВІДПОВІДАЛЬНІСТЮ \"АЛЬФА\". ЄДРПОУ 35197641. Стан: зареєстровано.\n") * 200


def _tokenizer(tmp: Path):
    corpus = tmp / "toy.txt"
    corpus.write_text(TOY, encoding="utf-8")
    return train_lm.train_tokenizer(corpus, vocab=500, out=tmp / "tok.json")


def test_tokenizer_train_and_encode():
    with tempfile.TemporaryDirectory() as tmp:
        tok = _tokenizer(Path(tmp))
        ids = tok.encode("Суд: Шостий апеляційний суд.").ids
        assert ids and tok.decode(ids).startswith("Суд")
        assert tok.token_to_id("<pad>") is not None


def test_model_forward_and_generate():
    torch.manual_seed(0)
    with tempfile.TemporaryDirectory() as tmp:
        tok = _tokenizer(Path(tmp))
        model = train_lm.GPT(vocab=tok.get_vocab_size(), dim=32, layers=2, heads=2, ctx=32)
        assert model.num_params() < 200_000
        x = torch.randint(0, tok.get_vocab_size(), (2, 16))
        logits = model(x)
        assert logits.shape == (2, 16, tok.get_vocab_size())
        text = train_lm.generate(model, tok, "Суд: ", 32, "cpu", max_new=4)
        assert isinstance(text, str)
