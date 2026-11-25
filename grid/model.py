"""Pin one approved registry artifact at task start and score pressure levels in batches."""

import gzip
import hashlib
import io
import json
from datetime import timedelta

from ml.artifact import read_artifact
from ml.features import vector
from services.forecast.model_tile import CELLS, NAMES, NO_DATA, NO_FEATURE, SCHEMA, WIDTH_BYTES
from services.forecast.product import unpack
from services.forecast.schema import CATEGORIES, LEVELS, issue_time, tile_name
from services.forecast.storage import checked_tile


def load_approved(sm, store, group):
    found = sm.list_model_packages(
        ModelPackageGroupName=group,
        ModelApprovalStatus="Approved",
        SortBy="CreationTime",
        SortOrder="Descending",
        MaxResults=1,
    )["ModelPackageSummaryList"]
    if not found:
        return None
    package = sm.describe_model_package(ModelPackageName=found[0]["ModelPackageArn"])
    if package["ModelApprovalStatus"] != "Approved" or package["ModelPackageGroupName"] != group:
        return None
    url = package["InferenceSpecification"]["Containers"][0]["ModelDataUrl"]
    prefix = f"s3://{store.bucket}/ml/runs/"
    if not url.startswith(prefix) or not url.endswith("/output/model.tar.gz"):
        raise ValueError("Registry artifact is outside the SkyCalm training prefix")
    archive = store.read(url.removeprefix(f"s3://{store.bucket}/"), 5_000_000)
    text, metadata = read_artifact(io.BytesIO(archive))
    meta = json.loads(metadata)
    if (
        meta["schema"] != SCHEMA
        or meta["features"] != list(NAMES)
        or meta["classes"] != list(CATEGORIES)
        or hashlib.sha256(text).hexdigest() != meta["sha256"]
    ):
        raise ValueError("Incompatible approved model")
    import lightgbm as lgb

    return lgb.Booster(model_str=text.decode()), {
        "version": package["ModelPackageVersion"],
        "sha256": meta["sha256"],
    }


def score_tile(booster, cube, month):
    import numpy as np

    output = np.full((len(LEVELS) * CELLS, WIDTH_BYTES), NO_DATA, dtype=np.uint8)
    for level in range(len(LEVELS)):
        rows, cells = [], []
        for cell in range(CELLS):
            row = vector(cube, cell, level, month)
            if row is not None:
                cells.append(level * CELLS + cell)
                rows.append(row)
        if not rows:
            continue
        data = np.asarray(rows)
        probs = booster.predict(data, num_threads=1)
        contributions = booster.predict(data, pred_contrib=True, num_threads=1).reshape(
            len(rows), 4, len(NAMES) + 1
        )
        # Passenger categories use the same byte-quantized probabilities that appear in the tile.
        quantized = np.rint(probs * 255).astype(np.uint8)
        winners = quantized.argmax(axis=1)
        effects = contributions[np.arange(len(rows)), winners, :-1]
        output[cells, :4] = quantized
        output[cells, 4] = np.where(effects.max(axis=1) > 0, effects.argmax(axis=1), NO_FEATURE)
    return gzip.compress(output.tobytes(), compresslevel=6, mtime=0)


def add_predictions(directory, manifest, model):
    if model is None:
        return
    booster, identity = model
    issued = issue_time(manifest["runId"])
    for lead in manifest["leads"]:
        n = lead["lead"]
        source = checked_tile((directory / tile_name(n)).read_bytes(), lead["sha256"])
        prediction = score_tile(booster, unpack(source), (issued + timedelta(hours=n)).month)
        (directory / f"ml-{n:03}.gz").write_bytes(prediction)
        lead["modelSha256"] = hashlib.sha256(prediction).hexdigest()
    manifest["model"] = identity | {"schema": SCHEMA}
