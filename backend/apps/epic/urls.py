from django.urls import path

from .views import (
    AuthFinishView,
    AuthStartView,
    ConnectionsView,
    ConnectionSyncView,
    OrganizationsView,
    SyncJobView,
)

urlpatterns = [
    path("organizations", OrganizationsView.as_view(), name="epic-organizations"),
    path("auth/start", AuthStartView.as_view(), name="epic-auth-start"),
    path("auth/finish", AuthFinishView.as_view(), name="epic-auth-finish"),
    path("connections", ConnectionsView.as_view(), name="epic-connections"),
    path("connections/<int:connection_id>/sync", ConnectionSyncView.as_view(), name="epic-connection-sync"),
    path("sync/<int:job_id>", SyncJobView.as_view(), name="epic-sync-job"),
]
