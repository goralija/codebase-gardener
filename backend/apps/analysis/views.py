from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.analysis import storage_service
from apps.analysis.fixtures import load_first_report_fixture
from apps.analysis.serializers import FirstReportFixtureSerializer
from apps.common.api import api_error_response
from apps.repositories.models import ManagedRepository


@api_view(["GET"])
@permission_classes([AllowAny])
def first_report(_request):
    """Latest stored analysis as a FirstReport, falling back to the fixture.

    NOTE: AllowAny + latest-across-all-repos is a dev/demo affordance. Production
    serving must scope by authenticated organization (E05-T01 / E02-T06).
    """
    latest = storage_service.get_latest_any()
    if latest is not None:
        payload = storage_service.load_first_report(latest)
    else:
        try:
            payload = load_first_report_fixture()
        except ImproperlyConfigured:
            return api_error_response(
                "server_configuration_error",
                "First report fixture is not available.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    serializer = FirstReportFixtureSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    return Response(serializer.validated_data)


@api_view(["GET"])
@permission_classes([AllowAny])
def repository_report(_request, repository_id):
    """Latest stored analysis for one repository as a FirstReport.

    NOTE: AllowAny for local testing; production must scope by membership.
    """
    repository = ManagedRepository.objects.filter(id=repository_id).first()
    if repository is None:
        return api_error_response(
            "not_found", "Repository not found.", status_code=status.HTTP_404_NOT_FOUND
        )

    latest = storage_service.get_latest(repository)
    if latest is None:
        return api_error_response(
            "no_analysis",
            "No analysis has been stored for this repository yet.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    payload = storage_service.load_first_report(latest)
    serializer = FirstReportFixtureSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    return Response(serializer.validated_data)


@api_view(["GET"])
@permission_classes([AllowAny])
def repository_baseline_report(_request, repository_id):
    """Latest promoted baseline analysis for one repository as a FirstReport.

    NOTE: AllowAny for local testing; production must scope by membership.
    """
    repository = ManagedRepository.objects.filter(id=repository_id).first()
    if repository is None:
        return api_error_response(
            "not_found", "Repository not found.", status_code=status.HTTP_404_NOT_FOUND
        )

    baseline = storage_service.get_latest_relevant_baseline(repository)
    if baseline is None:
        return api_error_response(
            "no_baseline_analysis",
            "No baseline analysis has been promoted for this repository yet.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    payload = storage_service.load_first_report(baseline)
    serializer = FirstReportFixtureSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    return Response(serializer.validated_data)
