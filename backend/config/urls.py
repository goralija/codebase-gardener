from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health(_request):
    return Response(
        {
            "status": "ok",
            "service": "codebase-gardener-backend",
            "version": "0.1.0",
        }
    )


urlpatterns = [
    path("api/v1/health/", health, name="health"),
    path("api/v1/reports/", include("apps.analysis.urls")),
]
