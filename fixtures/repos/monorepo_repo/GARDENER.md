# Repository Constitution

## Product Purpose

Monorepo Repo demonstrates logical systems and boundary rules.

## Architecture Boundaries

- `apps/web/**` may import `packages/shared/**`.
- `apps/web/**` must call `apps/api/**` through HTTP clients, not direct persistence imports.
- `apps/api/**` owns persistence and domain rules.

## Protected Modules

- API persistence: `apps/api/src/db/**`

## Ignored Paths

- `apps/web/dist/**`
- `node_modules/**`
