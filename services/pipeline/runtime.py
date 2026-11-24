"""Regional clients shared inside a warm Lambda invocation environment."""

import os
from functools import lru_cache

import boto3
from botocore.config import Config

from services.forecast.aws import AwsStore


@lru_cache
def session():
    return boto3.Session(region_name=os.environ.get("AWS_REGION", "eu-north-1"))


CONFIG = Config(
    connect_timeout=3, read_timeout=8, retries={"mode": "standard", "total_max_attempts": 3}
)


@lru_cache
def client(service):
    return session().client(service, config=CONFIG)


@lru_cache
def table():
    return session().resource("dynamodb", config=CONFIG).Table(os.environ["PIPELINE_TABLE"])


@lru_cache
def weather():
    return AwsStore.from_env()
