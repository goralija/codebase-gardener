# Security and Compliance

> Status: Ground truth
> Purpose: Define initial security expectations for Gardener.

## Security principles

- Minimize GitHub App permissions.
- Isolate customer organization and repository data.
- Avoid storing raw source code unless the feature requires it.
- Encrypt installation tokens, credentials, and sensitive configuration.
- Never leak code, secrets, or private repo data into logs.
- Treat PR creation as a privileged action.
- Treat source-truth files as customer-controlled policy, not as trusted executable input.

## Repository access

Workers may read repository content only for selected repositories and only through the GitHub App installation.

Worker writes should be limited to:

- branches
- PRs
- PR comments
- proposed updates to `GARDENER.md` and `.gardener/profile.yaml`
- status/check reporting

## Protected areas

By default, do not modify:

- auth
- payments
- pricing
- permissions
- business workflows
- migrations
- security-sensitive code
- customer-defined protected modules

## Audit requirements

Audit:

- installation changes
- repository selection changes
- autonomy policy changes
- trigger/schedule changes
- constitution answer changes
- profile/memory updates
- PR creation attempts
- worker failures affecting customer repos

## Compliance posture

V1 should implement normal SaaS security hygiene. Advanced enterprise compliance and regional hosting are future work unless required by a large customer.

## Light security maintenance

Security is part of codebase maintenance, so v1 should include light dependency and dangerous-pattern signals. Do not present v1 as a full security platform.
