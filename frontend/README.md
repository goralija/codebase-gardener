# Codebase Gardener Frontend

Vite, React, TypeScript, TanStack Query/Router/Form, Valibot, and shadcn/ui with preset `bLToCnFy`.

The first screen consumes the DRF first-report API using `VITE_API_BASE_URL`. Root `make dev` and `.env.example` point Vite at `http://localhost:8000/api/v1`; if unset, the frontend falls back to same-origin `/api/v1`.

## Commands

```bash
VITE_API_BASE_URL=http://localhost:8000/api/v1 pnpm dev
pnpm test -- --run
pnpm build
pnpm exec playwright test
```
