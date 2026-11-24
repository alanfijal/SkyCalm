from functools import lru_cache

from services.forecast.aws import AwsStore
from services.forecast.http import response


@lru_cache(maxsize=1)
def store() -> AwsStore:
    return AwsStore.from_env()


def handler(event: dict, context) -> dict:
    http = event["requestContext"]["http"]
    return response(
        http["method"],
        event["rawPath"],
        event.get("rawQueryString", ""),
        store(),
        context.aws_request_id,
    )
