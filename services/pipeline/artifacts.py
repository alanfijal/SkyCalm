"""Read only the artifacts produced by this pipeline job."""

from services.forecast.aws import AwsStore
from services.forecast.storage import checked_tile
from services.pipeline.contract import parse_job


class StagedGrid(AwsStore):
    def __init__(self, base: AwsStore, job: dict):
        super().__init__(base.s3, base.bucket, base.table)
        self.job = parse_job(job)

    def prefix(self, run_id: str) -> str:
        if run_id != self.job["runId"]:
            raise ValueError("Wrong forecast run for this job")
        if self.job["mode"] == "replay":
            return f"pipeline/jobs/{self.job['jobId']}/"
        return super().prefix(run_id)

    def manifest(self, run_id: str) -> dict | None:
        return self.published_manifest(run_id)

    def tile(self, run_id: str, lead: int, digest: str) -> bytes:
        return checked_tile(self.read(self.prefix(run_id) + digest + ".bin.gz", 300_000), digest)

    def advance(self, run_id: str) -> None:
        # The workflow promotes a complete live manifest. Replays have a private namespace.
        if run_id != self.job["runId"]:
            raise ValueError("Wrong forecast run for this job")
