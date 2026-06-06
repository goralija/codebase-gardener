from rest_framework import serializers

from apps.accounts.models import CustomerOrganization


class CustomerOrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerOrganization
        fields = [
            "id",
            "name",
            "github_login",
            "github_account_type",
        ]
