"""Session trigger kinds and policy constants (E04-T02).

A single registry of trigger kinds keeps the webhook handlers, the manual
service entrypoint, and the scheduled dispatcher in agreement about the trigger
vocabulary, the kinds that require an actor, and the roles allowed to trigger a
session manually.
"""

from __future__ import annotations

from apps.accounts.models import Membership

MANUAL = "manual"
SCHEDULE = "schedule"
N_COMMITS = "n_commits"
RISKY_MODULE = "risky_module"
PR_OPENED = "pr_opened"
CI_FAILURE = "ci_failure"
PUSH = "push"
FIRST_SCAN = "first_scan"

TRIGGER_KINDS = frozenset(
    {
        MANUAL,
        SCHEDULE,
        N_COMMITS,
        RISKY_MODULE,
        PR_OPENED,
        CI_FAILURE,
        PUSH,
        FIRST_SCAN,
    }
)

# Kinds initiated by an authenticated user; subject to permission policy.
ACTOR_REQUIRED_KINDS = frozenset({MANUAL})

# Kinds that warrant an audit-trail entry when enqueued. Covers actor-initiated
# (manual), protected-area (risky_module), and automated schedule triggers per
# docs/11 "trigger/schedule changes" audit requirement.
AUDITED_KINDS = frozenset({MANUAL, RISKY_MODULE, SCHEDULE})

# Organization roles permitted to trigger a session manually.
MANUAL_TRIGGER_ROLES = frozenset(
    {
        Membership.Role.OWNER,
        Membership.Role.ADMIN,
        Membership.Role.MAINTAINER,
    }
)
