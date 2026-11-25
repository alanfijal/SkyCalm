"""Measure held-out performance and decide whether an artifact may be promoted."""

import argparse
import json
from pathlib import Path

from services.forecast.schema import CATEGORIES

MIN_SUPPORT = 5


def metrics(labels, probabilities):
    matrix = [[0] * 4 for _ in CATEGORIES]
    bins = [[[0, 0, 0.0] for _ in range(5)] for _ in CATEGORIES]
    for target, p in zip(labels, probabilities, strict=True):
        winner = max(range(4), key=lambda i: p[i])
        matrix[target][winner] += 1
        for i, value in enumerate(p):
            cell = bins[i][min(int(value * 5), 4)]
            cell[0] += 1
            cell[1] += int(target == i)
            cell[2] += float(value)
    per_class = {}
    for k, name in enumerate(CATEGORIES):
        support = sum(matrix[k])
        predicted = sum(row[k] for row in matrix)
        true = matrix[k][k]
        per_class[name] = {
            "support": support,
            "precision": true / predicted if predicted else None,
            "recall": true / support if support else None,
            "f1": 2 * true / (support + predicted) if support + predicted else 0.0,
            "calibration": [
                {"bin": i, "count": n, "meanProbability": total / n, "observedRate": yes / n}
                for i, (n, yes, total) in enumerate(bins[k])
                if n
            ],
        }
    return {
        "rows": len(labels),
        "confusion": matrix,
        "classes": per_class,
        "macroF1": sum(v["f1"] for v in per_class.values()) / 4 if labels else None,
    }


def approval(sectors):
    reasons = []
    for name in ("europe", "north_atlantic"):
        s = sectors[name]
        if any(c["support"] < MIN_SUPPORT for c in s["model"]["classes"].values()):
            reasons.append(
                f"{name}: fewer than {MIN_SUPPORT} held-out examples in at least one class"
            )
        for category in ("moderate", "severe"):
            a = s["model"]["classes"][category]["recall"]
            b = s["baseline"]["classes"][category]["recall"]
            if a is not None and b is not None and a < b:
                reasons.append(f"{name}: {category} recall fell below the baseline")
    eu = sectors["europe"]
    if eu["model"]["macroF1"] is None or eu["model"]["macroF1"] <= eu["baseline"]["macroF1"]:
        reasons.append("European macro F1 did not improve")
    return {"status": "PendingManualApproval" if reasons else "Approved", "reasons": reasons}


def evaluate(data, model, output):
    import lightgbm as lgb
    import pyarrow.parquet as pq

    from ml.train import arrays

    rows = pq.read_table(data / "test.parquet").to_pylist()
    booster = lgb.Booster(model_file=str(model / "model.txt"))
    probs = booster.predict(arrays(rows)[0], num_threads=1).tolist()
    result = {}
    for area in ("all", "europe", "north_atlantic"):
        selected = [i for i, row in enumerate(rows) if area == "all" or row["sector"] == area]
        labels = [rows[i]["label"] for i in selected]
        baseline = [[float(c == rows[i]["baseline"]) for c in range(4)] for i in selected]
        result[area] = {
            "model": metrics(labels, [probs[i] for i in selected]),
            "baseline": metrics(labels, baseline),
        }
    report = {
        "sectors": result,
        "approval": approval(result),
        "dataset": json.loads((data / "dataset.json").read_bytes()),
        "model": json.loads((model / "model.json").read_bytes()),
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "evaluation.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report["approval"]))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for key in ("data", "model", "output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    evaluate(args.data, args.model, args.output)
