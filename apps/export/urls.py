from django.urls import path
from export.views import export


urlpatterns = [
    path("export/", export, name="export")
]
