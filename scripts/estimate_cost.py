"""Estimate gross Stockholm costs for four bounded SkyCalm workloads, in USD."""

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class Workload:
    days: int
    runs: int
    polling_hours: int
    visits: int
    users: int
    training_cycles: int
    storage_gb: float
    logs_gb: float
    management_events: int
    flow_dns_gb: float


SCENARIOS = {
    "Demo day": Workload(
        days=1,
        runs=2,
        polling_hours=1,
        visits=5,
        users=1,
        training_cycles=0,
        storage_gb=8,
        logs_gb=0.03,
        management_events=1_000,
        flow_dns_gb=0.02,
    ),
    "Idle month": Workload(
        days=30,
        runs=0,
        polling_hours=0,
        visits=0,
        users=0,
        training_cycles=0,
        storage_gb=8,
        logs_gb=0.05,
        management_events=10_000,
        flow_dns_gb=0.05,
    ),
    "Demo month": Workload(
        days=30,
        runs=24,
        polling_hours=12,
        visits=100,
        users=20,
        training_cycles=1,
        storage_gb=8,
        logs_gb=0.5,
        management_events=20_000,
        flow_dns_gb=0.2,
    ),
    "Continuous": Workload(
        days=30,
        runs=120,
        polling_hours=720,
        visits=500,
        users=50,
        training_cycles=1,
        storage_gb=25,
        logs_gb=3,
        management_events=100_000,
        flow_dns_gb=2,
    ),
}


def estimate(w: Workload, *, private_azs: int = 0) -> dict[str, float]:
    """Return costs by service group. Zero AZs selects the public-subnet design."""
    if private_azs not in (0, 1, 2):
        raise ValueError("Select a public subnet (0) or private endpoints in 1 or 2 AZs")

    month = w.days / 30
    hours = w.days * 24
    grid_hours = w.runs * 6 / 60
    polls = w.polling_hours * (30 + 4)  # OpenSky every 2 min, AWC every 15 min
    requests = w.visits * 10
    edge_requests = w.visits * 60
    fanout = w.runs * 30  # watched flights in the 36-hour window
    messages = 1.25 * (fanout + w.runs * 2 + w.users * 2)
    lambda_calls = 1.25 * (requests + fanout * 3 + polls + w.runs * 6 + w.users * 2)
    idle_receives = 3 * 5 * hours * 3_600 / 20
    processed_gb = w.runs * 0.30  # measured weather payload + index/retry allowance
    briefings = w.visits * 2
    kms_ops = w.training_cycles * 2_000

    if private_azs:
        endpoint_hours = 4 * private_azs * hours
        endpoint_gb = w.runs * 1.05  # image and logs per task
        # External NOAA fetch staged into Stockholm by a non-VPC worker.
        staging = w.runs * (120 * 0.0000133334 + 13 * 0.000005 + 13 * 0.0000002)
        network = endpoint_hours * 0.0105 + endpoint_gb * 0.01 + staging
    else:
        network = grid_hours * 0.005

    return {
        "WAF (ACL, two rules, requests)": 7 * month + edge_requests * 0.60 / 1e6,
        "Network (IP or endpoints + relay)": network,
        "Fargate CPU and memory": grid_hours * (0.0445 + 2 * 0.0049),
        "S3, ECR and DynamoDB storage": month * (w.storage_gb * 0.023 + 0.10 + 0.25 * 0.269),
        "S3 requests and transfer allowance": (
            w.runs * 200 * 0.000005 + (requests + w.runs * 350) * 0.0000004 + processed_gb * 0.09
        ),
        "HTTP API, Lambda and DynamoDB I/O": (
            requests * 1.06 / 1e6
            + lambda_calls * 0.20 / 1e6
            + lambda_calls * 0.5 * 0.5 * 0.0000133334
            + (fanout * 6 + polls + w.users * 8) * 0.67 / 1e6
            + (requests * 6 + fanout * 10) * 0.1345 / 1e6
        ),
        "SQS, EventBridge and Step Functions": (
            (idle_receives + messages * 3) * 0.40 / 1e6
            + messages / 1e6
            + (polls + w.users * 2) / 1e6
            + (w.runs * 24 + w.training_cycles * 30) * 0.000025
        ),
        "CloudFront and origin signing": (
            w.visits * 0.015 * 0.085
            + edge_requests * 0.012 / 10_000
            + requests * (0.60 / 1e6 + 0.128 * 0.03 * 0.00005001)
        ),
        "Cognito, SES and Secrets Manager": (
            w.users * 0.015
            + w.users * 4 * 0.0001
            + 3 * 0.40 * month
            + (polls + w.users * 4) * 0.05 / 10_000
        ),
        "CloudWatch, CloudTrail and GuardDuty": (
            month * (6 * 0.10 + 0.30)
            + w.logs_gb * (0.54 + 0.03)
            + w.management_events * 0.0000042
            + w.flow_dns_gb * 1.05
        ),
        "SageMaker jobs, volumes and KMS": (
            w.training_cycles * (2 * 0.122 + 30 / 720 * (0.10 + 0.146))
            + month
            + kms_ops * 0.03 / 10_000
        ),
        "Bedrock, Glue and Athena": (
            briefings * (0.5 * 0.000065 + 0.08 * 0.00026)
            + 25 * month / 100_000
            + w.visits * 0.05 / 1_000 * 5
        ),
    }


def cost_table() -> str:
    estimates = [estimate(scenario) for scenario in SCENARIOS.values()]
    lines = [
        "| USD before credits | " + " | ".join(SCENARIOS) + " |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name in estimates[0]:
        values = " | ".join(f"{result[name]:.2f}" for result in estimates)
        lines.append(f"| {name} | {values} |")
    for label, azs in (
        ("Total · public", 0),
        ("Total · private, 1 AZ", 1),
        ("Total · private, 2 AZs", 2),
    ):
        totals = [
            sum(estimate(scenario, private_azs=azs).values()) for scenario in SCENARIOS.values()
        ]
        values = " | ".join(f"**{total:.2f}**" for total in totals)
        lines.append(f"| **{label}** | {values} |")
    return "\n".join(lines)


if __name__ == "__main__":
    print(cost_table())
