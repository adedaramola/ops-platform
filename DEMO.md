# Portfolio demonstration

The primary demo proves integration without collapsing repository boundaries.

## Local deterministic demo

```bash
docker compose up --build -d
docker compose --profile demo run --rm seed
```

Sign in as the seeded support agent, claim a ticket, and request a draft. With deterministic fake
dependencies, verify that the request returns immediately, the suggestion remains pending, and the
ticket remains usable if AI is disabled. Edit and approve the suggestion, then apply it once and
confirm the public comment and immutable activity/review history.

## Connected demo

Configure OpsDesk/Agent with the independently deployed RAG Platform search URL and scoped API key,
plus the independently deployed multi-LLM gateway URL and scoped caller key. Do not copy either
service's state or credentials into this repository.

1. Create a ticket whose answer is covered by an approved RAG source.
2. Request an AI draft and capture the workflow ID—not the ticket text—in the demo notes.
3. Confirm SQS dispatch and Agent consumption under that workflow ID and trace ID.
4. Confirm RAG Platform returns bounded evidence with citation IDs from the approved source list.
5. Confirm the gateway records bounded provider/model, latency, token, cost, and cache-policy data.
6. Review the OpsDesk draft, citation metadata, and source/page display.
7. Edit and approve as a human agent, apply once, and verify replay does not duplicate the comment.
8. Follow the workflow on the platform dashboard across queue, RDS, RAG Platform, and gateway.
9. Disable or break one optional AI dependency and show that ordinary ticket operations and core
   readiness remain healthy.

## Honest demo boundaries

Do not imply that a local fake result is a live model call, that a logical dump proves RDS PITR, or
that Terraform validation proves an AWS apply. Do not display secrets, internal notes, raw prompts,
queries, evidence excerpts, account IDs, private endpoints, or customer data in screenshots.
