import gzip
import json

import pytest

from grid.model import load_approved
from services.forecast.briefing import cache_key, choose_with_bedrock, select, variants
from services.forecast.model_tile import CELLS, WIDTH_BYTES, decode_predictions, point_prediction
from services.forecast.schema import LEVELS


def test_grid_without_approved_model_leaves_weather_on_physics():
    class Registry:
        def list_model_packages(self, **kwargs):
            assert kwargs["ModelApprovalStatus"] == "Approved" and kwargs["MaxResults"] == 1
            return {"ModelPackageSummaryList": []}

    assert load_approved(Registry(), None, "skycalm-turbulence") is None


def test_compact_predictions_keep_missing_levels_and_explain_selected_class():
    cube = [-32768] * (17 * CELLS)
    cube[2 * CELLS] = 10000
    fields = bytearray([255]) * (len(LEVELS) * CELLS * WIDTH_BYTES)
    fields[:5] = bytes([12, 145, 80, 18, 1])
    pt = {"lat": 34, "lon": -25, "altitudeFt": 33000}
    pred = point_prediction(decode_predictions(gzip.compress(fields)), cube, pt)
    assert pred["category"] == "light" and pred["driver"] == "wind changing with height"
    assert 0.56 < pred["probability"] < 0.58
    assert point_prediction(fields, cube, pt | {"altitudeFt": 500}) == {}
    with pytest.raises(ValueError):
        decode_predictions(gzip.compress(b"incomplete"))


def test_briefing_rejects_invented_details_and_keys_each_forecast():
    choices = variants(
        [
            {"phase": "cruise", "category": "moderate"},
            {"phase": "descent", "category": "unavailable"},
        ]
    )

    class Client:
        def __init__(self, text):
            self.text = text

        def converse(self, **kwargs):
            assert kwargs["inferenceConfig"]["maxTokens"] <= 24
            assert "EDI" not in json.dumps(kwargs)
            return {
                "stopReason": "end_turn",
                "output": {"message": {"content": [{"text": self.text}]}},
            }

    assert "moderate" in select(choices, choose_with_bedrock(Client("[1,0]"), "example", choices))
    for invalid in ('"It will be safe."', "[2,0]", "[true,false]", "[0]"):
        with pytest.raises(ValueError):
            choose_with_bedrock(Client(invalid), "example", choices)
    assert cache_key("run", "EDI", "OPO", "12Z", choices) != cache_key(
        "run", "EDI", "OPO", "14Z", choices
    )


def test_sagemaker_tar_accepts_dot_prefix_and_rejects_duplicate_metadata():
    import io
    import tarfile

    from ml.artifact import read_artifact

    def archive(names):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as tar:
            for name in names:
                body = b"data"
                member = tarfile.TarInfo(name)
                member.size = len(body)
                tar.addfile(member, io.BytesIO(body))
        output.seek(0)
        return output

    assert read_artifact(archive(["./model.txt", "./model.json"])) == (b"data", b"data")
    with pytest.raises(ValueError):
        read_artifact(archive(["model.txt", "model.json", "./model.json"]))
