from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0009_alter_auditevent_event_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("github_installation_synced", "GitHub installation synced"),
                    ("managed_repository_selected", "Managed repository selected"),
                    ("managed_repository_unselected", "Managed repository unselected"),
                    (
                        "managed_repository_hard_deleted",
                        "Managed repository hard deleted",
                    ),
                    ("maintenance_pr_created", "Maintenance PR created"),
                    (
                        "maintenance_pr_creation_failed",
                        "Maintenance PR creation failed",
                    ),
                    (
                        "maintenance_pr_outcome_recorded",
                        "Maintenance PR outcome recorded",
                    ),
                    ("gardener_profile_updated", "Gardener profile updated"),
                    ("gardener_profile_pr_proposed", "Gardener profile PR proposed"),
                    ("gardener_profile_pr_failed", "Gardener profile PR failed"),
                    ("analysis_stored", "Repository analysis stored"),
                    ("repository_complexity_updated", "Repository complexity updated"),
                    ("billing_subscription_updated", "Billing subscription updated"),
                    ("automation_policy_updated", "Automation policy updated"),
                    ("session_trigger_enqueued", "Session trigger enqueued"),
                    ("session_trigger_failed", "Session trigger failed"),
                    ("session_canceled", "Session canceled"),
                    ("maintenance_prs_authored", "Maintenance PRs authored"),
                ],
                max_length=64,
            ),
        ),
    ]
