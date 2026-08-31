# Limitations

- The portfolio environment is nonproduction and may be intentionally paused to control cost.
- AWS deployment, RDS snapshot/PITR restore, DNS, and live cross-service smoke tests require owner
  approval and are not implied by local validation.
- Staff MFA, email verification, account recovery, breached-password screening, attachments,
  malware scanning, and customer-data retention workflows are not implemented.
- RAG Platform ingestion governance and network hardening remain in its separate repository.
- Multi-LLM provider correctness, pricing, quotas, and model behavior remain external dependencies.
- AI suggestions can be wrong or manipulated; citations support review but do not make a response
  trustworthy. A human must approve every consequential application.
- CloudWatch/Application Signals and dashboard costs must be reviewed before enabling them broadly.
- SLOs are initial portfolio objectives and need representative traffic before being treated as an
  operational commitment.
