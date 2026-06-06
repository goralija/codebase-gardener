# Architecture

## Logical Systems

- API: `apps/api/**`
- Web: `apps/web/**`
- Shared contracts: `packages/shared/**`

## Boundaries

The web app must not import API persistence modules directly.
