from rest_framework import serializers

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
        ]
