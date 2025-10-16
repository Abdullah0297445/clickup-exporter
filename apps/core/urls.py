from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path(
        "api/v1/",
        include(
            [
                path("", include("export.urls")),
            ]
        ),
    ),
]
