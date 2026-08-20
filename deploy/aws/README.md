# AWS deployment runbook

## Recommended architecture

Use Route 53 and ACM for DNS/TLS, an internet-facing Application Load Balancer protected
by AWS WAF, and an ECS service running one Uvicorn process per Fargate task in private
subnets. Place RDS PostgreSQL in isolated private subnets with Multi-AZ enabled. The API
needs controlled outbound HTTPS through NAT for OpenAI. Store `DATABASE_URL`,
`OPENAI_API_KEY`, and `SITE_CONFIG_JSON` in Secrets Manager. Send container stdout to
CloudWatch Logs.

The widget can initially be cached through the ALB/CloudFront route. At higher volume,
publish the immutable `widget.js` asset to a private S3 origin behind CloudFront while
keeping API requests routed to the ALB.

## Provisioning checklist

1. Create a VPC spanning at least two Availability Zones.
2. Put the ALB in public subnets, ECS tasks in private subnets, and RDS in isolated
   database subnets.
3. Allow the ALB security group to reach ECS port 8000. Allow the ECS security group to
   reach only the RDS port. Do not expose ECS or RDS directly to the internet.
4. Create RDS PostgreSQL, enable encryption, automated backups, deletion protection, and
   `pgvector`. Confirm the exact pgvector version supported by the chosen RDS engine.
5. Create an ECR repository and a CloudWatch log group with an explicit retention period.
6. Put the three runtime secrets shown in `ecs-task-definition.example.json` in Secrets
   Manager. Grant the execution role access only to those secret ARNs.
7. Replace every account, region, host, image, cluster, and service placeholder in the
   example files.
8. Configure the ALB target health check as `/api/ready`; use `/api/health` only for
   container liveness.
9. Configure WAF rate-based rules, managed rule groups, and request-size restrictions.
10. Configure ECS target-tracking scaling for CPU/memory and use at least two tasks across
    Availability Zones.

## Build and release

```bash
docker build --pull -t flooring-chatbot:${IMAGE_TAG} .

aws ecr get-login-password --region ${AWS_REGION} \
  | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
docker tag flooring-chatbot:${IMAGE_TAG} \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/flooring-chatbot:${IMAGE_TAG}
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/flooring-chatbot:${IMAGE_TAG}
```

Run `flooring-migrate` as a one-off ECS task using the new image before updating the ECS
service. It applies idempotent catalog/session migrations and the LangGraph-owned
checkpoint migrations. Never run catalog ingestion or bulk embedding generation inside
every API task startup.

Deploy an immutable image digest or unique tag, wait for target health, run smoke tests,
then terminate the old task set. Roll back by restoring the previous task definition and
image; database migrations in this repository are additive and idempotent.

## Monitoring and alarms

Import `cloudwatch-dashboard.example.json` after replacing placeholders. Create alarms for:

- ALB healthy host count below the desired ECS task count.
- Sustained target 5xx errors or p95 target latency above the business SLO.
- ECS CPU or memory saturation and task restart count.
- RDS CPU, free storage, connections, replication lag, and failover events.
- Log events with `recommendation service is temporarily unavailable` or failed readiness.
- Secrets rotation, WAF blocks, and unusual request volume.

Structured logs contain request IDs, routes, status, duration, site/session identifiers,
actions, and result counts. They deliberately exclude customer message content, API keys,
database URLs, prompts, and complete product payloads.

## Capacity and performance

- Size `DATABASE_POOL_MAX_SIZE × ECS task count` below the RDS connection budget.
- Load test `/api/chat` with realistic OpenAI latency before selecting task CPU/memory.
- Track candidate count, OpenAI latency/error rate, database query latency, and p95/p99 API
  latency. Add provider-specific telemetry only after confirming it does not capture text.
- Keep the pgvector HNSW index analyzed and monitor recall/latency as the catalog grows.
- Cache `widget.js` at CloudFront; do not cache session or chat responses.
- Run catalog ingestion and embedding updates as separate bounded ECS tasks or scheduled
  jobs, not in request-serving tasks.
- Schedule `flooring-sync` as an EventBridge-triggered ECS task. Use
  `--authoritative-snapshot` only for a verified complete feed, alert on non-zero exit,
  and monitor the latest `catalog_sync_runs` status and record counts.
- Run `flooring-evaluate` in CI and before changing ranking weights or flooring rules.

## Backup and recovery

Enable automated RDS backups and point-in-time recovery, take a manual snapshot before
major catalog/schema operations, and test restoration into a separate environment.
Conversation sessions and LangGraph checkpoints share PostgreSQL and follow the same
retention/recovery plan. Schedule deletion of expired sessions and old checkpoints based
on the business retention policy.
