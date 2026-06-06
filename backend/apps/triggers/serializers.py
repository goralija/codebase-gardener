from rest_framework import serializers

from apps.triggers.models import RepositoryAutomationPolicy


class RepositoryAutomationPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = RepositoryAutomationPolicy
        fields = [
            "id",
            "autonomy_mode",
            "manual_trigger_enabled",
            "scheduled_trigger_enabled",
            "commit_trigger_enabled",
            "risky_module_trigger_enabled",
            "pr_opened_trigger_enabled",
            "ci_failure_trigger_enabled",
            "commit_threshold",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
