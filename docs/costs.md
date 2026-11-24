# What will the classroom demo cost?

**24 November 2026 · USD · Stockholm.** The proposed temporary-IP design costs **$13.41** for twelve rehearsals across a 30-day month. One fully provisioned demo day costs **$0.51** when it reuses an existing model. A quiet month still costs **$11.35**, primarily for WAF, secrets, a key and monitoring. These are planning estimates before credits, tax and free allowances. Phase 0 created no AWS resources.

## Workload

| Input | Demo day | Idle month | Demo month | Continuously refreshed month |
| --- | ---: | ---: | ---: | ---: |
| Days installed / grid runs | 1 / 2 | 30 / 0 | 30 / 24 | 30 / 120 |
| Hours of feed polling | 1 | 0 | 12 | 720 |
| Passenger visits / monthly active users | 5 / 1 | 0 / 0 | 100 / 20 | 500 / 50 |
| Training cycles / average raw + curated S3 GB | 0 / 8 | 0 / 8 | 1 / 8 | 1 / 25 |
| Log ingestion GB / foundational flow and DNS GB | .03 / .02 | .05 / .05 | .5 / .2 | 3 / 2 |
| GuardDuty management events | 1,000 | 10,000 | 20,000 | 100,000 |

The continuous scenario admits all four GFS cycles every day and runs the approved feeds throughout the month. It illustrates a schedule left enabled. Traffic floods, runaway training and unrelated account activity fall outside that estimate. For each scenario, a task runs six minutes at 1 x86 vCPU / 2 GiB, with one temporary IPv4 address. The desired **classroom replay** has a separate three-minute end-to-end target and needs performance measurements. A demo day includes a day's share of fixed resources and a full month's charge for its single active user.

## Gross estimate

| USD before credits | Demo day | Idle month | Demo month | Continuous |
| --- | ---: | ---: | ---: | ---: |
| WAF (ACL, two rules, requests) | 0.23 | 7.00 | 7.00 | 7.02 |
| Network (IP or endpoints + relay) | 0.00 | 0.00 | 0.01 | 0.06 |
| Fargate CPU and memory | 0.01 | 0.00 | 0.13 | 0.65 |
| S3, ECR and DynamoDB storage | 0.01 | 0.35 | 0.35 | 0.74 |
| S3 requests and transfer allowance | 0.06 | 0.00 | 0.68 | 3.38 |
| HTTP API, Lambda and DynamoDB I/O | 0.00 | 0.00 | 0.02 | 0.23 |
| SQS, EventBridge and Step Functions | 0.03 | 0.78 | 0.80 | 0.89 |
| CloudFront and origin signing | 0.01 | 0.00 | 0.14 | 0.68 |
| Cognito, SES and Secrets Manager | 0.06 | 1.20 | 1.51 | 2.09 |
| CloudWatch, CloudTrail and GuardDuty | 0.07 | 1.02 | 1.48 | 5.13 |
| SageMaker jobs, volumes and KMS | 0.03 | 1.00 | 1.26 | 1.26 |
| Bedrock, Glue and Athena | 0.00 | 0.00 | 0.04 | 0.18 |
| **Total · public** | **0.51** | **11.35** | **13.41** | **22.30** |
| **Total · private, 1 AZ** | **1.54** | **41.59** | **43.93** | **53.94** |
| **Total · private, 2 AZs** | **2.55** | **71.83** | **74.17** | **84.18** |

Run `python3 scripts/estimate_cost.py` to reproduce this table. Rows round independently. A displayed $0.00 can include a fraction of a cent.

## What drives the bill

- **Networking and weather.** Regional list prices are $0.0445/vCPU-hour and $0.0049/GiB-hour for Linux x86 Fargate, $0.005/public IPv4-hour, and $0.0105/interface endpoint-AZ-hour plus $0.01/GB processed. Four interfaces × two AZs × 720 h = **$60.48** before bytes. One AZ costs $30.24 and loses AZ redundancy. If the grid needs only ECR API, ECR Docker and Logs, three interfaces across two AZs still cost $45.36. Both designs use free S3/DynamoDB regional gateways. The private comparison includes a non-VPC NOAA relay (120 GB-seconds plus 13 small writes and invocations per run) and 1.05 GB/task of image/log endpoint traffic. Both include **0.30 GB/run at $0.09/GB as a conservative transfer allowance**. The observed 13-lead GFS selection was 0.187 GB before retries. Dataset sponsorship, payer and network path can reduce this allowance. [Fargate regional price list](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonECS/current/eu-north-1/index.json) · [Stockholm VPC price list](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonVPC/current/eu-north-1/index.json) · [AWS data transfer](https://aws.amazon.com/ec2/pricing/on-demand/#Data_Transfer)
- **Delivery and compute.** Allow 10 HTTP requests and 60 edge requests per visit, 15 MB of EU CDN egress per visit, 30 watched flights/run, 25% extra message/worker invocations for retries, 24 workflow transitions/run and 30 transitions/training cycle. Base Lambda calls use 512 MiB for 0.5 seconds. Each licensed polling hour includes 30 OpenSky and 4 AWC fetches. Budget three SQS source mappings with five pollers each and 20-second long polls even when idle. SNS filter volume and actual empty receives require measurement. CDN uses pay-as-you-go EU rates; the signer runs on origin requests, here conservatively one per API request. [HTTP API regional list](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonApiGateway/current/eu-north-1/index.json) · [Lambda](https://aws.amazon.com/lambda/pricing/) · [EventBridge](https://aws.amazon.com/eventbridge/pricing/) · [Step Functions](https://aws.amazon.com/step-functions/pricing/) · [SQS](https://aws.amazon.com/sqs/pricing/) · [CloudFront](https://aws.amazon.com/cloudfront/pricing/pay-as-you-go/)
- **Data, users and ML.** S3 Standard is $0.023/GB-month. Include storage versions in the GB total, 200 writes/run and ECR image storage of 1 GB. Assume 0.25 GB of DynamoDB, on-demand reads/writes, three secrets, up to four SES emails per active user and Cognito Essentials at $0.015/MAU. One ML cycle uses two half-hour Processing jobs and one one-hour Training job on `ml.m5.large` ($0.122/hour each), 30 GB temporary volumes and one project KMS key for the month. Each visit allows two Nova Lite cache misses (500 input and 80 output tokens each). Athena scans 50 MB/visit at $5/TB. Define roughly 25 catalog objects. Guard the workgroup at 100 MB/query and run queries on demand. [S3](https://aws.amazon.com/s3/pricing/) · [DynamoDB](https://aws.amazon.com/dynamodb/pricing/on-demand/) · [Cognito](https://aws.amazon.com/cognito/pricing/) · [SES](https://aws.amazon.com/ses/pricing/) · [SageMaker regional list](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonSageMaker/current/eu-north-1/index.json) · [Bedrock regional list](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/current/eu-north-1/index.json) · [Athena](https://aws.amazon.com/athena/pricing/)
- **Protection and audit.** Budget $5/month for a WAF ACL and $1 each for a rate rule and an AWS managed common rule group, plus $0.60/million requests. Six standard alarms at $0.10/month, one metric at $0.30 and logs at $0.54/GB plus a conservative storage allowance cover the classroom signals. Foundational GuardDuty is priced at $4.20/million management events and $1.05/GB flow/DNS volume. It observes the account in the selected region. Extra protection plans can change the bill. Use existing CloudTrail management-event history or the first management-event trail copy, with S3 log bytes included above. Data events, additional trail copies and CloudTrail Lake have separate charges. [WAF](https://aws.amazon.com/waf/pricing/) · [CloudWatch](https://aws.amazon.com/cloudwatch/pricing/) · [Stockholm GuardDuty list](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonGuardDuty/current/eu-north-1/index.json) · [CloudTrail](https://aws.amazon.com/cloudtrail/pricing/) · [KMS](https://aws.amazon.com/kms/pricing/)
- **Outside these figures.** VAT after any plan change, external data licences, a custom domain, email/push providers' contractual charges, extra weather history for global ML training and inter-region user-data processing require separate review. Maintain a hard byte/job/time limit for historical extraction before pricing Phase 5. The estimate assumes a reusable training set in the quoted S3 footprint. Dedicated IPs, NAT, Studio apps, real-time endpoints, extra GuardDuty features and monthly model tuning are disabled. [Free account conditions](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html)

## Credit checks and stopping costs

The account API reported an active Free plan on 24 November. The owner receives the exact balance and plan end date privately. AWS says eligible use on this plan draws down available credits and that the plan closes at expiry or exhaustion. **Expected cash exposure from eligible AWS usage while this plan stays active: $0.** A blocked service needs a scope decision. A paid account, ineligible external service or different billing arrangement changes the cash exposure. Recheck eligibility and gross usage before each deployment. [AWS Free plan](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html)

Keep the project target at $25 gross in total, the rehearsal month under $15 and at least $50 of verified credits in reserve. Two full demo months would exceed the total target. Request authorization for one monthly account-wide, pre-credit cost budget with actual alerts at $10/$25/$50 before initial deployment. Track gross project-to-date spend separately across month boundaries, alongside remaining credits. Budget alerts arrive after usage. Set one environment, one concurrent grid task, a 10-minute hard task deadline, bounded retries and explicit rehearsal windows. [Budget pricing](https://aws.amazon.com/aws-cost-management/aws-budgets/pricing/) · [Budget updates](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)

Between rehearsals, close admission, disable feed/schedule triggers and stop active grid tasks. Retain state so Terraform can reconcile resumption. To stop fixed charges, review an application destroy plan covering WAF, interfaces (if any), alarms, secrets, job resources and the ML key. Include noncurrent S3 versions, ECR images, logs and retained model artifacts in cleanup. A retained 1 GB of demo weather is about $0.023/month, plus requests. The versioned state bucket and any retained replay archive survive until the owner approves export and separate removal. Preserve original data licences and team backups.
