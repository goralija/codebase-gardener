from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.analysis.fixtures import load_first_report_fixture
from apps.analysis.serializers import FirstReportFixtureSerializer
from apps.common.api import api_error_response


@api_view(["GET"])
@permission_classes([AllowAny])
def first_report(_request):
    try:
        fixture = load_first_report_fixture()
    except ImproperlyConfigured:
        return api_error_response(
            "server_configuration_error",
            "First report fixture is not available.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    serializer = FirstReportFixtureSerializer(data=fixture)
    serializer.is_valid(raise_exception=True)
    return Response(serializer.validated_data)
