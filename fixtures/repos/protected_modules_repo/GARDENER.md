# Repository Constitution

## Product Purpose

Protected Modules Repo tests safety handling for sensitive code.

## Protected Modules

- Authentication: `src/auth/**`
- Billing: `src/billing/**`

## Never-Touch Paths

- `src/billing/payment_engine.py` because payment behavior requires human-owned review.

## Autonomous Fixes Allowed

- Documentation updates outside protected modules.
- Test additions outside never-touch paths.

## Advisory-Only Areas

- Auth.
- Billing.

## Test Rules

Run `pytest tests/` for any source change.
