from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
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
]

