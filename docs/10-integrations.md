# Integrations

> Status: Ground truth
> Purpose: Define v1 integration expectations.

## V1 integrations

### GitHub

GitHub is the required v1 integration and product surface.

Use GitHub REST through Python HTTP clients. GraphQL can be considered later only when REST cannot provide the needed data efficiently.

Gardener must use GitHub for:

- app installation
- repository selection
- webhook triggers
- branch creation
- PR creation
- PR comments
- check/status reporting
- reading repository files and history
- detecting PR outcomes

### Repowise fork

Gardener should fork Repowise into the project and use it as the repository-intelligence foundation.

The fork should provide or evolve:

- graph intelligence
- git intelligence
- health signals
- dead-code detection
- documentation and decision intelligence where useful
- monorepo and logical-system support

### Light security/dependency sources

V1 includes light security as part of maintenance. Full Snyk-style support is not v1 scope.

Potential sources:

- package manifests and lockfiles
- GitHub Dependabot alerts where available
- GitHub security advisories where available
- local pattern checks for obvious dangerous code

## Later integrations

- Snyk or equivalent vulnerability platforms.
- GitLab and Bitbucket.
- Slack notifications.
- Jira issue creation or linking.
- Customer-hosted/self-hosted deployment channels for large customers.

## Integration rules

- Integrations must be organization and repository scoped.
- Credentials must be encrypted.
- Webhooks must be idempotent.
- GitHub webhook signatures must be verified before processing.
- Failures must be visible in sessions and dashboards.
- External write actions must be audited.
- Gardener must not request broader provider permissions than the enabled feature requires.
