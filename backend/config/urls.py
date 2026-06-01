from django.contrib import admin
from django.urls import include, path

from apps.epic.views import HealthView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", HealthView.as_view(), name="health"),
    # Platform identity endpoints (standalone local login + partner-token + me)
    path("api/v1/auth/", include("apps.accounts.urls")),
    # Epic / MyChart connector (contract preserved from the FastAPI service)
    path("epic/", include("apps.epic.urls")),
]
