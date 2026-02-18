from django.urls import path
from django.views.generic import RedirectView

from admin_portal import views

app_name = "admin_portal"

urlpatterns = [
    path("login/", RedirectView.as_view(pattern_name="core:login", permanent=False), name="login"),
    path("logout/", RedirectView.as_view(pattern_name="core:logout", permanent=False), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("users/", views.users_list, name="users_list"),
    path("users/create/", views.user_create, name="users_create"),
    path("users/<int:user_id>/edit/", views.user_edit, name="users_edit"),
    path("users/<int:user_id>/lock/", views.user_lock, name="users_lock"),
    path("users/<int:user_id>/unlock/", views.user_unlock, name="users_unlock"),
    path("audit/", views.audit_log, name="audit"),
    path("interviews/", views.interview_approvals, name="interview_approvals"),
    path("interviews/<int:interview_id>/approve/", views.interview_approve, name="interview_approve"),
]
