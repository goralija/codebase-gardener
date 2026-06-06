from rest_framework import serializers


class SubscriptionUpdateSerializer(serializers.Serializer):
    autonomous_pr_add_on_enabled = serializers.BooleanField(required=False)
    plan_code = serializers.CharField(required=False, allow_blank=False, max_length=64)
    base_price_cents = serializers.IntegerField(required=False, min_value=0)
    autonomous_pr_add_on_price_cents = serializers.IntegerField(
        required=False,
        min_value=0,
    )

    def validate(self, attrs):
        allowed_fields = {
            "autonomous_pr_add_on_enabled",
            "plan_code",
            "base_price_cents",
            "autonomous_pr_add_on_price_cents",
        }
        unknown_fields = set(self.initial_data) - allowed_fields
        if unknown_fields:
            raise serializers.ValidationError(
                {
                    field: "Unknown billing field."
                    for field in sorted(unknown_fields)
                }
            )
        if not attrs:
            raise serializers.ValidationError("At least one billing field is required.")
        return attrs
