from celery import shared_task

from apps.github_app.client import RETRYABLE_STATUS_CODES, GitHubAPIError
from apps.maintenance_prs.ci_repair import repair_failed_maintenance_pr_plan
from apps.maintenance_prs.executor import execute_maintenance_pr_plan
from apps.maintenance_prs.models import MaintenancePRPlan


@shared_task(bind=True, max_retries=3)
def execute_pr_plan(self, plan_id: str) -> dict[str, object]:
    plan = MaintenancePRPlan.objects.get(id=plan_id)
    try:
        result = execute_maintenance_pr_plan(plan)
    except GitHubAPIError as exc:
        if exc.status_code in RETRYABLE_STATUS_CODES and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=0)
        raise

    return {
        "plan_id": str(plan.id),
        "execution_status": result["execution_status"],
        "pr_number": result["created_pr_number"],
    }


@shared_task(bind=True, max_retries=1)
def repair_failed_maintenance_pr(
    self,
    maintenance_pr_plan_id: str,
    webhook_event_id: str | None = None,
) -> dict:
    return repair_failed_maintenance_pr_plan(
        plan_id=maintenance_pr_plan_id,
        webhook_event_id=webhook_event_id,
    )
