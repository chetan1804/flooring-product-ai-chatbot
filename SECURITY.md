# Security review

## Implemented controls

- Secrets are environment-only and excluded from Git and the container image.
- Site domains and browser origins come from a validated server registry.
- Sessions use server-generated UUIDs, are site-bound, expire, and are durable in
  PostgreSQL in the production runtime.
- Product URLs are generated from registered domains and catalog SKUs, never by an LLM.
- SQL uses fixed statements with bound parameters; LLM output cannot select SQL fields.
- LLM structured output is validated and mapped to current catalog vocabulary.
- Request payloads, site codes, UUIDs, and response models are validated with Pydantic.
- Host headers, CORS origins, request body size, OpenAI timeouts/retries, and database pool
  bounds are configurable and validated.
- Production API docs are disabled by default. Responses include request IDs, MIME-sniffing
  protection, a restrictive referrer policy, permissions policy, and HSTS.
- Widget text is inserted with DOM `textContent`; links are restricted to HTTP(S) and use
  `noopener noreferrer`.
- JSON logs omit customer text, secrets, prompts, and complete catalog records.
- Strict LangGraph MessagePack deserialization is mandatory in production.
- The container runs as a non-root user with an optional read-only root filesystem.

## Required infrastructure controls

- Terminate TLS with ACM at ALB/CloudFront and redirect HTTP to HTTPS.
- Restrict ECS ingress to the ALB security group and RDS ingress to the ECS security group.
- Use AWS WAF rate-based and managed rules; enforce a request-size limit at the edge.
- Encrypt RDS, ECR, CloudWatch Logs, and Secrets Manager with managed or customer keys.
- Use least-privilege task/execution roles and rotate database/OpenAI secrets.
- Enable CloudTrail, GuardDuty, ECR image scanning, dependency scanning, and protected CI.
- Pin releases by image digest and require reviewed migrations before deployment.

## Residual risks and operating decisions

- Recommendation quality depends on source catalog accuracy and OpenAI availability.
- Browser origin checks are not authentication for non-browser clients. Add authenticated
  service credentials if the API is offered directly to third parties.
- Application-level rate limiting is intentionally delegated to centralized AWS WAF so it
  is consistent across ECS tasks.
- Conversation/checkpoint retention requires a scheduled cleanup policy aligned with
  privacy and business requirements.
- Prompt injection is constrained by structured extraction and deterministic retrieval,
  ranking, and URL generation, but adversarial testing should continue with model changes.

Report vulnerabilities privately to the repository owner. Do not include credentials,
customer conversations, or production database contents in an issue.
