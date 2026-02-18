from django.urls import path
from django.views.generic import RedirectView

from hr_portal import views

app_name = "hr_portal"

urlpatterns = [
    path("login/", RedirectView.as_view(pattern_name="core:login", permanent=False), name="login"),
    path("logout/", RedirectView.as_view(pattern_name="core:logout", permanent=False), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("employees/", views.employees, name="employees"),
    path("requests/profile/", views.profile_requests, name="profile_requests"),
    path(
        "requests/profile/<int:request_id>/<str:decision>/",
        views.profile_request_decision,
        name="profile_request_decision",
    ),
    path("requests/leave/", views.leave_requests, name="leave_requests"),
    path(
        "requests/leave/<int:leave_id>/<str:decision>/",
        views.leave_request_decision,
        name="leave_request_decision",
    ),
    path("tasks/control/", views.task_control, name="task_control"),
    path("tasks/create/", views.task_create, name="task_create"),
    path("tasks/<int:task_id>/status/", views.task_set_status, name="task_set_status"),
    path("interviews/", views.interviews, name="interviews"),
    path("interviews/create/", views.interview_create, name="interview_create"),
    path("interviews/<int:interview_id>/edit/", views.interview_edit, name="interview_edit"),
    path("interviews/<int:interview_id>/send/", views.interview_send_to_admin, name="interview_send"),
    path("interviews/<int:interview_id>/tg-link/", views.interview_telegram_link, name="interview_tg_link"),
    path("schedule/", views.schedule, name="schedule"),
    path("schedule/create/", views.schedule_create, name="schedule_create"),
    path("schedule/<int:shift_id>/reassign/", views.schedule_reassign, name="schedule_reassign"),
]
