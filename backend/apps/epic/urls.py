from django.urls import path

from .views import AuthFinishView, AuthStartView, OrganizationsView

urlpatterns = [
    path("organizations", OrganizationsView.as_view(), name="epic-organizations"),
    path("auth/start", AuthStartView.as_view(), name="epic-auth-start"),
    path("auth/finish", AuthFinishView.as_view(), name="epic-auth-finish"),
]
