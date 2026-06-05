# Deployment and Environments

> Status: Ground truth
> Purpose: Define deployment expectations for the hosted GitHub App product.

## V1 deployment model

V1 is Gardener-hosted:

- hosted web dashboard
- hosted Django/DRF API
- hosted Celery background workers
- hosted scheduler
- hosted PostgreSQL database
- hosted Redis broker/cache
- GitHub App integration

Customer-hosted/local deployment is not part of the standard v1 offer. It may be offered later for large customers that demand it.

## Environments

- Development: local engineering environment.
- Staging: connected to a staging GitHub App and non-production data.
- Production: connected to production GitHub App installations.

## Required services

The chosen stack must support:

- GitHub webhook ingestion
- Celery background jobs
- scheduled jobs through Celery Beat or an equivalent scheduler
- secure token storage
- persistent analysis snapshots
- repository checkout or API-based file access
- hosted dashboard/API
- logs, metrics, and error tracking

## Worker requirements

- Isolate customer sessions.
- Limit runtime and resource usage.
- Clean up temporary repository checkouts.
- Avoid cross-customer cache leakage.
- Persist failures with enough detail to debug without leaking code or secrets.

## Monitoring

Track:

- webhook failures
- session durations
- worker failures
- PR creation failures
- scoring failures
- GitHub API rate limit pressure
- customer-facing latency
- entropy report generation time

## Implementation stack

The implementation stack is fixed in `docs/18-technical-architecture.md`. The concrete hosting provider remains open.
