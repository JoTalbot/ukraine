#!/usr/bin/env python3
"""Train a small Ukrainian legal-domain language model from scratch.

CPU-friendly GPT (PyTorch) + byte-level BPE tokenizer (tokenizers).

Pipeline: corpus.txt -> BPE -> token memmap -> GPT training with periodic
holdout evaluation and sample generation -> checkpoint + metrics.

Example:
    python scripts/train_lm.py --corpus corpus.txt --out artifacts/lm \
        --steps 2000 --dim 256 --layers 6 --ctx 256 --batch 8
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers
from torch import nn

DEFAULT_VOCAB = 8192


# ---------------------------------------------------------------- model

class Block(nn.Module):
    def __init__(self, dim: int, heads: int):
        super().__init__()
        self.ln1 = nn.LayerNorm(dim)
        self.attn = nn.MultiheadAttention(dim, heads, batch_first=True)
        self.ln2 = nn.LayerNorm(dim)
        self.mlp = nn.Sequential(nn.Linear(dim, 4 * dim), nn.GELU(), nn.Linear(4 * dim, dim))

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        h = self.ln1(x)
        a, _ = self.attn(h, h, h, attn_mask=mask, need_weights=False)
        x = x + a
        return x + self.mlp(self.ln2(x))


class GPT(nn.Module):
    def __init__(self, vocab: int, dim: int, layers: int, heads: int, ctx: int):
        super().__init__()
        self.ctx = ctx
        self.tok = nn.Embedding(vocab, dim)
        self.pos = nn.Embedding(ctx, dim)
        self.blocks = nn.ModuleList(Block(dim, heads) for _ in range(layers))
        self.ln = nn.LayerNorm(dim)
        self.head = nn.Linear(dim, vocab, bias=False)
        self.head.weight = self.tok.weight  # tied embeddings
        mask = torch.triu(torch.full((ctx, ctx), float("-inf")), diagonal=1)
        self.register_buffer("mask", mask, persistent=False)

    def forward(self, idx: torch.Tensor) -> torch.Tensor:
        _, length = idx.shape
        x = self.tok(idx) + self.pos(torch.arange(length, device=idx.device))
        for block in self.blocks:
            x = block(x, self.mask[:length, :length])
        return self.head(self.ln(x))

    def num_params(self) -> int:
        return sum(p.numel() for p in self.parameters())


# ---------------------------------------------------------------- data

def train_tokenizer(corpus: Path, vocab: int, out: Path) -> Tokenizer:
    tok = Tokenizer(models.BPE(unk_token="<unk>"))  # noqa: S106 -- не секрет, спецтокен разметки
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tok.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(
        vocab_size=vocab,
        special_tokens=["<pad>", "<unk>"],
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
    )
    tok.train(files=[str(corpus)], trainer=trainer)
    tok.save(str(out))
    return Tokenizer.from_file(str(out))


def encode_file(tok: Tokenizer, corpus: Path, out: Path) -> np.memmap:
    pad_id = tok.token_to_id("<pad>")
    separator = bytes([pad_id & 0xFF, (pad_id >> 8) & 0xFF]) if pad_id is not None else b"\x00\x00"
    chunk: list[str] = []
    written = 0
    with out.open("wb") as sink:
        def flush() -> None:
            nonlocal written, chunk
            if not chunk:
                return
            for encoded in tok.encode_batch(chunk):
                arr = np.array(encoded.ids, dtype=np.uint16)
                sink.write(arr.tobytes())
                sink.write(separator)  # document separator token
                written += len(encoded.ids) + 1
            chunk = []
        with corpus.open("r", encoding="utf-8") as fh:
            for line in fh:
                chunk.append(line.rstrip("\n"))
                if len(chunk) >= 2000:
                    flush()
        flush()
    return np.memmap(str(out), dtype=np.uint16, mode="r", shape=(written,))


# ---------------------------------------------------------------- train

@torch.no_grad()
def evaluate(model: GPT, data: np.memmap, batch: int, ctx: int, device) -> float:
    model.eval()
    losses = []
    g = torch.Generator().manual_seed(123)
    n = len(data) - ctx - 1
    for _ in range(16):
        starts = torch.randint(0, max(n, 1), (batch,), generator=g).tolist()
        x = torch.tensor(np.stack([data[s:s + ctx] for s in starts]).astype(np.int64), device=device)
        y = torch.tensor(np.stack([data[s + 1:s + 1 + ctx] for s in starts]).astype(np.int64), device=device)
        logits = model(x)
        losses.append(F.cross_entropy(logits.view(-1, logits.size(-1)), y.view(-1)).item())
    model.train()
    return sum(losses) / len(losses)


@torch.no_grad()
def generate(model: GPT, tok: Tokenizer, prompt: str, ctx: int, device, max_new: int = 120, temperature: float = 0.9) -> str:
    model.eval()
    pad = tok.token_to_id("<pad>")
    ids = tok.encode(prompt).ids[-ctx:]
    x = torch.tensor([ids], dtype=torch.long, device=device)
    for _ in range(max_new):
        logits = model(x[:, -ctx:])[:, -1, :] / temperature
        probs = F.softmax(logits, dim=-1)
        next_id = torch.multinomial(probs, 1)
        x = torch.cat([x, next_id], dim=1)
        if next_id.item() == pad:
            break
    model.train()
    return tok.decode(x[0].tolist()).replace("<pad>", "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--vocab", type=int, default=DEFAULT_VOCAB)
    ap.add_argument("--dim", type=int, default=256)
    ap.add_argument("--layers", type=int, default=6)
    ap.add_argument("--ctx", type=int, default=256)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--steps", type=int, default=2000)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--warmup", type=int, default=100)
    ap.add_argument("--eval-every", type=int, default=200)
    ap.add_argument("--sample-every", type=int, default=400)
    ap.add_argument("--prompts", nargs="*", default=["Суд: ", "ТОВАРИСТВО З ОБМЕЖЕНОЮ ВІДПОВІДАЛЬНІСТЮ ", "Справа № "])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--device", default="cpu", help="cpu | cuda (auto: cuda when available)")
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    import os
    if args.device == "cuda" and not torch.cuda.is_available():
        print("cuda requested but not available; falling back to cpu")
        args.device = "cpu"
    device = args.device
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1))) if device == "cpu" else None
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    tok_path = out / "tokenizer.json"
    if tok_path.exists():
        tok = Tokenizer.from_file(str(tok_path))
    else:
        print("Training BPE tokenizer…", flush=True)
        # The trainer holds word frequencies in memory; a large sample is
        # enough for a stable vocabulary and keeps RAM flat on small hosts.
        sample = out / "corpus.sample.txt"
        if not sample.exists():
            with Path(args.corpus).open("r", encoding="utf-8") as src, sample.open("w", encoding="utf-8") as dst:
                for index, line in enumerate(src):
                    if index >= 250_000:
                        break
                    dst.write(line)
        tok = train_tokenizer(sample, args.vocab, tok_path)
    vocab = tok.get_vocab_size()
    print(f"tokenizer: {vocab} merges/tokens", flush=True)

    ids_path = out / "tokens.uint16"
    if ids_path.exists():
        data = np.memmap(str(ids_path), dtype=np.uint16, mode="r")
    else:
        print("Encoding corpus…", flush=True)
        data = encode_file(tok, Path(args.corpus), ids_path)
    print(f"corpus tokens: {len(data):,}", flush=True)

    if device == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)} capability={torch.cuda.get_device_capability(0)}", flush=True)
    model = GPT(vocab, args.dim, args.layers, max(1, args.dim // 64), args.ctx).to(device)
    print(f"model params: {model.num_params():,}", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, betas=(0.9, 0.95), weight_decay=0.1)

    def lr_at(step: int) -> float:
        if step < args.warmup:
            return args.lr * (step + 1) / args.warmup
        progress = (step - args.warmup) / max(1, args.steps - args.warmup)
        return args.lr * 0.5 * (1 + math.cos(math.pi * progress))

    metrics_path = out / "metrics.jsonl"
    samples_path = out / "samples.txt"
    g = torch.Generator().manual_seed(args.seed)
    n = len(data) - args.ctx - 1
    start_time = time.time()
    with metrics_path.open("a", encoding="utf-8") as metrics, samples_path.open("a", encoding="utf-8") as samples:
        for step in range(1, args.steps + 1):
            for group in opt.param_groups:
                group["lr"] = lr_at(step - 1)
            starts = torch.randint(0, n, (args.batch,), generator=g).tolist()
            x = torch.tensor(np.stack([data[s:s + args.ctx] for s in starts]).astype(np.int64), device=device)
            y = torch.tensor(np.stack([data[s + 1:s + 1 + args.ctx] for s in starts]).astype(np.int64), device=device)
            logits = model(x)
            loss = F.cross_entropy(logits.view(-1, logits.size(-1)), y.view(-1))
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()

            if step % 50 == 0 or step == 1:
                elapsed = time.time() - start_time
                entry = {"step": step, "loss": round(loss.item(), 4), "ppl": round(math.exp(min(loss.item(), 20)), 2),
                         "lr": round(lr_at(step - 1), 6), "sec": round(elapsed, 1)}
                metrics.write(json.dumps(entry) + "\n")
                metrics.flush()
                print(f"step {step:>5} loss {entry['loss']:.4f} ppl {entry['ppl']:.1f} ({elapsed:.0f}s)", flush=True)

            if args.eval_every and (step % args.eval_every == 0 or step == args.steps):
                val = evaluate(model, data, args.batch, args.ctx, device)
                metrics.write(json.dumps({"step": step, "val_loss": round(val, 4)}) + "\n")
                metrics.flush()
                print(f"step {step:>5} VAL loss {val:.4f}", flush=True)

            if args.sample_every and (step % args.sample_every == 0 or step == args.steps):
                samples.write(f"\n===== step {step} =====\n")
                for prompt in args.prompts:
                    text = generate(model, tok, prompt, args.ctx, device)
                    samples.write(f"[{prompt}] → {text}\n\n")
                samples.flush()

    torch.save({"model": model.state_dict(), "config": {"vocab": vocab, "dim": args.dim, "layers": args.layers,
                                                        "ctx": args.ctx}, "step": args.steps}, out / "model.pt")
    print("saved", out / "model.pt", flush=True)


if __name__ == "__main__":
    main()
