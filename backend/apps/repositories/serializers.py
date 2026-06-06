from rest_framework import serializers

from apps.billing.models import RepositoryComplexity
from apps.billing.services import repository_complexity_payload
from apps.github_app.models import GitHubInstallation
from apps.repositories.models import ManagedRepository


class GitHubInstallationSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = GitHubInstallation
        fields = [
            "id",
            "github_installation_id",
            "repository_selection",
            "html_url",
        ]


class ManagedRepositorySerializer(serializers.ModelSerializer):
    complexity = serializers.SerializerMethodField()

    class Meta:
        model = ManagedRepository
        fields = [
            "id",
            "github_repository_id",
            "name",
            "full_name",
            "owner_login",
            "private",
            "default_branch",
            "html_url",
            "selected_at",
            "complexity",
        ]

    def get_complexity(self, repository):
        try:
            complexity = repository.complexity
        except RepositoryComplexity.DoesNotExist:
            complexity = None
        return repository_complexity_payload(
            complexity,
            include_details=self.context.get("include_complexity_details", False),
        )
