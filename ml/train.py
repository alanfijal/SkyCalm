"""Train a deterministic four-class LightGBM candidate on the chronological training set."""

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pyarrow.parquet as pq

from services.forecast.model_tile import NAMES, SCHEMA
from services.forecast.schema import CATEGORIES


def arrays(rows):
    return np.asarray([[r[n] for n in NAMES] for r in rows]), np.asarray([r["label"] for r in rows])


def train(data, output, rounds=40):
    x, y = arrays(pq.read_table(data / "train.parquet").to_pylist())
    xv, yv = arrays(pq.read_table(data / "validation.parquet").to_pylist())
    counts = Counter(y.tolist())
    if len(counts) < 2 or not 1 <= rounds <= 64:
        raise ValueError("Training needs two observed classes and at most 64 boosting rounds")
    weights = [len(y) / (len(counts) * counts[int(i)]) for i in y]
    params = {
        "objective": "multiclass",
        "num_class": len(CATEGORIES),
        "metric": "multi_logloss",
        "learning_rate": 0.06,
        "num_leaves": 7,
        "min_data_in_leaf": 4,
        "num_threads": 1,
        "seed": 27,
        "deterministic": True,
        "force_col_wise": True,
        "verbosity": -1,
    }
    train_data = lgb.Dataset(x, label=y, weight=weights, feature_name=list(NAMES))
    valid = lgb.Dataset(xv, label=yv, reference=train_data)
    booster = lgb.train(
        params,
        train_data,
        num_boost_round=rounds,
        valid_sets=[valid],
        callbacks=[lgb.early_stopping(6, verbose=False)],
    )
    output.mkdir(parents=True, exist_ok=True)
    path = output / "model.txt"
    booster.save_model(str(path))
    metadata = {
        "schema": SCHEMA,
        "features": list(NAMES),
        "classes": list(CATEGORIES),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "iterations": booster.best_iteration,
    }
    (output / "model.json").write_text(json.dumps(metadata, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data", type=Path, default=os.getenv("SM_CHANNEL_TRAINING", "/opt/ml/input/data/training")
    )
    parser.add_argument("--output", type=Path, default=os.getenv("SM_MODEL_DIR", "/opt/ml/model"))
    parser.add_argument("--rounds", type=int, default=40)
    args = parser.parse_args()
    train(args.data, args.output, args.rounds)
