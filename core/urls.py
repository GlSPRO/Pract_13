from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("login/", views.GlobalLoginView.as_view(), name="login"),
    path("logout/", views.GlobalLogoutView.as_view(), name="logout"),
    path("integrations/telegram/webhook/", views.telegram_webhook, name="telegram_webhook"),
    path("employee/dashboard/", views.employee_dashboard, name="employee_dashboard"),
    path("employee/profile/", views.employee_profile, name="employee_profile"),
    path("employee/schedule/", views.employee_schedule, name="employee_schedule"),
    path("employee/schedule/<int:shift_id>/ack/", views.acknowledge_shift, name="employee_shift_ack"),
    path("employee/leave/", views.employee_leave_requests, name="employee_leave"),
    path("employee/tasks/", views.employee_tasks, name="employee_tasks"),
    path("employee/tasks/<int:task_id>/done/", views.complete_task, name="employee_task_done"),
    path("", views.root_redirect, name="root"),
]
