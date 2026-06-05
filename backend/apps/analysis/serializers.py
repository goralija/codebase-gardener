from rest_framework import serializers


class FirstReportFixtureSerializer(serializers.Serializer):
    repository_constitution = serializers.DictField()
    analysis_snapshot = serializers.DictField()
    entropy_report = serializers.DictField()
    gardening_session_result = serializers.DictField()
    maintenance_opportunities = serializers.ListField(child=serializers.DictField())
    maintenance_pr_plans = serializers.ListField(child=serializers.DictField())
