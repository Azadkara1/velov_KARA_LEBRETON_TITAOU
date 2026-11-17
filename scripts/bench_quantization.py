"""TP5a : DistilBERT en float32 contre int8, le triplet précision / latence / coût (S5).

Trois variantes du même modèle fine-tuné sur SST-2 :
    float32           le modèle publié
    int8 torch.ao     torch.ao.quantization.quantize_dynamic sur les nn.Linear
    int8 torchao      torchao quantize_ avec Int8DynamicActivationInt8WeightConfig

Pour chacune : taille du state_dict sérialisé, latence d'une phrase de 128 tokens sur un thread (p50, p95,
échauffement non compté), précision sur les 872 phrases de validation de SST-2 et accord avec float32.

    pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
    pip install -r requirements-quantization.txt
    python scripts/bench_quantization.py --out results/quantization
"""

from __future__ import annotations

import argparse
import copy
import io
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import torch
import torchao
import transformers
from huggingface_hub import hf_hub_download
from torchao.quantization import Int8DynamicActivationInt8WeightConfig, quantize_
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MODEL_ID = "distilbert-base-uncased-finetuned-sst-2-english"
SST2_REPO, SST2_FILE = "nyu-mll/glue", "sst2/validation-00000-of-00001.parquet"
SEQ_LEN = 128


def load_sst2() -> tuple[list[str], np.ndarray]:
    path = hf_hub_download(SST2_REPO, SST2_FILE, repo_type="dataset")
    table = pq.read_table(path)
    return table.column("sentence").to_pylist(), np.asarray(table.column("label").to_pylist())


def size_mb(model: torch.nn.Module) -> float:
    buffer = io.BytesIO()
    torch.save(model.state_dict(), buffer)
    return buffer.tell() / 1e6


@torch.inference_mode()
def latency_ms(model: torch.nn.Module, inputs: dict, n: int, warmup: int) -> tuple[float, float]:
    torch.set_num_threads(1)
    samples = []
    for i in range(warmup + n):
        t0 = time.perf_counter_ns()
        model(**inputs)
        if i >= warmup:
            samples.append((time.perf_counter_ns() - t0) / 1e6)
    return float(np.percentile(samples, 50)), float(np.percentile(samples, 95))


@torch.inference_mode()
def predict_all(model: torch.nn.Module, tokenizer, sentences: list[str], threads: int, batch: int = 32) -> np.ndarray:
    torch.set_num_threads(threads)  # la précision ne dépend pas du nombre de threads : on va plus vite
    preds = []
    for start in range(0, len(sentences), batch):
        enc = tokenizer(sentences[start:start + batch], padding=True, truncation=True, max_length=SEQ_LEN,
                        return_tensors="pt")
        preds.append(model(**enc).logits.argmax(dim=-1).numpy())
    return np.concatenate(preds)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=200, help="mesures de latence par variante")
    parser.add_argument("--warmup", type=int, default=10, help="itérations d'échauffement, non comptées")
    parser.add_argument("--threads-eval", type=int, default=torch.get_num_threads(), help="threads pour la précision")
    parser.add_argument("--out", type=Path, help="dossier où écrire resultats.json et tableau.md")
    args = parser.parse_args()

    torch.manual_seed(0)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    base = AutoModelForSequenceClassification.from_pretrained(MODEL_ID).eval()
    sentences, labels = load_sst2()

    # Une phrase réelle, complétée jusqu'à exactement 128 tokens.
    one = tokenizer(sentences[0], padding="max_length", truncation=True, max_length=SEQ_LEN, return_tensors="pt")
    assert one["input_ids"].shape == (1, SEQ_LEN)

    torchao_model = copy.deepcopy(base)
    quantize_(torchao_model, Int8DynamicActivationInt8WeightConfig())
    variants = {
        "float32": base,
        "int8 torch.ao (quantize_dynamic)": torch.ao.quantization.quantize_dynamic(
            copy.deepcopy(base), {torch.nn.Linear}, dtype=torch.qint8
        ),
        "int8 torchao": torchao_model,
    }

    rows, reference = [], None
    for name, model in variants.items():
        preds = predict_all(model, tokenizer, sentences, args.threads_eval)
        reference = preds if reference is None else reference
        p50, p95 = latency_ms(model, one, args.n, args.warmup)
        rows.append({
            "variante": name,
            "taille_mo": round(size_mb(model), 1),
            "p50_ms": round(p50, 1),
            "p95_ms": round(p95, 1),
            "precision": round(float((preds == labels).mean()), 4),
            "accord_float32": round(float((preds == reference).mean()), 4),
            "desaccords": int((preds != reference).sum()),
        })
        print(f"{name} : fait", file=sys.stderr)

    protocole = {
        "date_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "machine": platform.processor() or platform.machine(),
        "python": platform.python_version(),
        "torch": torch.__version__, "transformers": transformers.__version__, "torchao": torchao.__version__,
        "modele": MODEL_ID, "donnees": f"{SST2_REPO} {SST2_FILE} ({len(sentences)} phrases)",
        "latence": f"1 phrase de {SEQ_LEN} tokens, 1 thread, {args.warmup} échauffements puis {args.n} mesures",
    }
    table = ["| variante | taille Mo | p50 ms | p95 ms | précision SST-2 | accord float32 | désaccords |",
             "|---|---|---|---|---|---|---|"]
    table += [f"| {r['variante']} | {r['taille_mo']} | {r['p50_ms']} | {r['p95_ms']} | {r['precision']:.2%} "
              f"| {r['accord_float32']:.2%} | {r['desaccords']} |" for r in rows]
    print("\n".join(f"{k} : {v}" for k, v in protocole.items()) + "\n\n" + "\n".join(table))

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "resultats.json").write_text(json.dumps({"protocole": protocole, "variantes": rows},
                                                            ensure_ascii=False, indent=2), encoding="utf-8")
        (args.out / "tableau.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
