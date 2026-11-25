"""Produce one cached briefing for a public demo route using the Stockholm Nova Lite model."""

import argparse
import json
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from services.forecast.api import respond
from services.forecast.briefing import cache_key, choose_with_bedrock, select, variants
from services.forecast.storage import LocalStore

MODEL = "amazon.nova-lite-v1:0"


def main():
    p = argparse.ArgumentParser()
    for key in ("run", "origin", "destination", "departure"):
        p.add_argument("--" + key, required=True)
    p.add_argument("--cache", type=Path, default=Path(".local/weather/briefings"))
    p.add_argument("--bedrock", action="store_true", help="Make one regional model request")
    p.add_argument(
        "--publish",
        action="store_true",
        help="Store this approved demo briefing in the SkyCalm weather bucket",
    )
    args = p.parse_args()
    store = LocalStore(args.cache.parent)
    query = {key: getattr(args, key) for key in ("run", "origin", "destination", "departure")}
    route = respond("/api/forecast", query, store)
    opts = variants(route["samples"])
    key = cache_key(
        args.run, route["origin"]["code"], route["destination"]["code"], route["departure"], opts
    )
    cfg = Config(connect_timeout=3, read_timeout=12, retries={"total_max_attempts": 1})
    session = boto3.Session(region_name="eu-north-1")
    if args.bedrock or args.publish:
        if session.client("sts", config=cfg).get_caller_identity()["Account"] != "028718095604":
            raise SystemExit("Wrong AWS account")
    path = args.cache / (key + ".json")
    cached = json.loads(path.read_bytes()) if path.is_file() else None
    result = cached or {"source": "template", "choices": [0, 0]}
    if args.bedrock and result["source"] != "bedrock":
        try:
            choices = choose_with_bedrock(
                session.client("bedrock-runtime", config=cfg), MODEL, opts
            )
            result = {"source": "bedrock", "choices": choices}
        except (BotoCoreError, ClientError, ValueError, KeyError, IndexError) as exc:
            print(f"Using the template after {type(exc).__name__}.")
    print(select(opts, result["choices"]))
    args.cache.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result) + "\n")
    if args.publish:
        session.client("s3", config=cfg).put_object(
            Bucket="skycalm-dev-weather-028718095604-eu-north-1",
            Key=f"ml/briefings/{key}.json",
            Body=path.read_bytes(),
            ContentType="application/json",
        )


if __name__ == "__main__":
    main()
