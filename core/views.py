import json
import secrets

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from admin_portal.models import AuditLog
from admin_portal.utils import employee_required, is_admin, is_employee, is_hr
from core.forms import LeaveRequestForm, ProfileChangeRequestForm
from core.telegram_utils import send_telegram_message
from core.models import EmployeeTask, LeaveRequest, Profile, ProfileChangeRequest
from hr_portal.models import InterviewTelegramInvite
from hr_portal.models import ShiftAssignment


def _resolve_home_url(user):
    if is_admin(user):
        return "admin_portal:dashboard"
    if is_hr(user):
        return "hr_portal:dashboard"
    if is_employee(user):
        return "core:employee_dashboard"
    return None


class GlobalLoginView(LoginView):
    template_name = "auth/login.html"
    redirect_authenticated_user = True
    extra_context = {"hide_shell": True}

    def get_success_url(self):
        target = _resolve_home_url(self.request.user)
        return reverse(target) if target else reverse("core:login")

    def form_valid(self, form):
        response = super().form_valid(form)
        if not _resolve_home_url(self.request.user):
            messages.error(self.request, "У пользователя не назначена рабочая роль.")
            logout(self.request)
            return redirect("core:login")
        return response


class GlobalLogoutView(LogoutView):
    next_page = "core:login"
    http_method_names = ["get", "post", "options"]

    def get(self, request, *args, **kwargs):
        logout(request)
        return redirect("core:login")

    def post(self, request, *args, **kwargs):
        logout(request)
        return redirect("core:login")


def root_redirect(request):
    if not request.user.is_authenticated:
        return redirect("core:login")
    target = _resolve_home_url(request.user)
    if not target:
        logout(request)
        return redirect("core:login")
    return redirect(target)


@employee_required
def employee_dashboard(request):
    today = timezone.localdate()
    shifts = ShiftAssignment.objects.filter(assigned_employee=request.user).order_by("date", "start_time")
    upcoming = shifts.filter(date__gte=today)[:5]
    pending_tasks = request.user.employee_tasks.exclude(status=EmployeeTask.STATUS_DONE).count()
    leave_open = request.user.leave_requests.filter(status=LeaveRequest.STATUS_SUBMITTED).count()
    profile_pending = request.user.profile_change_requests.filter(
        status__in=[ProfileChangeRequest.STATUS_NEW, ProfileChangeRequest.STATUS_REVIEW]
    ).count()

    context = {
        "hide_shell": False,
        "portal_type": "employee",
        "active_section": "dashboard",
        "upcoming_shifts": upcoming,
        "kpis": [
            {"label": "Предстоящие смены", "value": upcoming.count()},
            {"label": "Невыполненные задачи", "value": pending_tasks},
            {"label": "Заявки по отпускам", "value": leave_open},
            {"label": "Заявки на профиль", "value": profile_pending},
        ],
    }
    return render(request, "employee/dashboard.html", context)


@employee_required
def employee_profile(request):
    profile, _ = Profile.objects.get_or_create(
        user=request.user,
        defaults={"full_name": request.user.username, "position": "Сотрудник"},
    )
    if request.method == "POST":
        form = ProfileChangeRequestForm(request.POST)
        if form.is_valid():
            req = form.save(commit=False)
            req.employee = request.user
            req.save()
            AuditLog.objects.create(
                actor=request.user,
                action="update",
                object_type="employee_profile_request",
                object_id=str(req.pk),
                details=f"Запрос на изменение профиля: {req.field_label}",
            )
            messages.success(request, "Заявка на изменение профиля отправлена.")
            return redirect("core:employee_profile")
    else:
        form = ProfileChangeRequestForm()

    requests = request.user.profile_change_requests.all()[:10]
    context = {
        "hide_shell": False,
        "portal_type": "employee",
        "active_section": "profile",
        "profile": profile,
        "experience_days": (timezone.localdate() - profile.created_at.date()).days if profile.created_at else 0,
        "form": form,
        "requests": requests,
    }
    return render(request, "employee/profile.html", context)


@employee_required
def employee_schedule(request):
    shifts = ShiftAssignment.objects.filter(assigned_employee=request.user).order_by("date", "start_time")
    context = {
        "hide_shell": False,
        "portal_type": "employee",
        "active_section": "schedule",
        "shifts": shifts,
    }
    return render(request, "employee/schedule.html", context)


@employee_required
def acknowledge_shift(request, shift_id: int):
    shift = get_object_or_404(ShiftAssignment, pk=shift_id, assigned_employee=request.user)
    if request.method == "POST":
        shift.is_acknowledged = True
        shift.acknowledged_at = timezone.now()
        shift.save(update_fields=["is_acknowledged", "acknowledged_at", "updated_at"])
        AuditLog.objects.create(
            actor=request.user,
            action="update",
            object_type="shift_assignment",
            object_id=str(shift.pk),
            details=f"Сотрудник подтвердил ознакомление со сменой {shift.date} {shift.start_time.strftime('%H:%M')}",
        )
        messages.success(request, "Ознакомление со сменой подтверждено.")
    return redirect("core:employee_schedule")


@employee_required
def employee_leave_requests(request):
    if request.method == "POST":
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave = form.save(commit=False)
            leave.employee = request.user
            leave.status = LeaveRequest.STATUS_SUBMITTED
            leave.save()
            AuditLog.objects.create(
                actor=request.user,
                action="create",
                object_type="leave_request",
                object_id=str(leave.pk),
                details=f"Создана заявка: {leave.get_leave_type_display()} {leave.start_date} - {leave.end_date}",
            )
            messages.success(request, "Заявка отправлена HR.")
            return redirect("core:employee_leave")
    else:
        form = LeaveRequestForm()

    leaves = request.user.leave_requests.all()[:15]
    context = {
        "hide_shell": False,
        "portal_type": "employee",
        "active_section": "leave",
        "form": form,
        "leaves": leaves,
    }
    return render(request, "employee/leave.html", context)


@employee_required
def employee_tasks(request):
    tasks = request.user.employee_tasks.order_by("status", "due_date", "-created_at")
    context = {
        "hide_shell": False,
        "portal_type": "employee",
        "active_section": "tasks",
        "tasks": tasks,
    }
    return render(request, "employee/tasks.html", context)


@employee_required
def complete_task(request, task_id: int):
    task = get_object_or_404(EmployeeTask, pk=task_id, employee=request.user)
    if request.method == "POST":
        task.status = EmployeeTask.STATUS_DONE
        task.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(
            actor=request.user,
            action="update",
            object_type="employee_task",
            object_id=str(task.pk),
            details=f"Задача отмечена как выполненная: {task.title}",
        )
        messages.success(request, "Задача отмечена как выполненная.")
    return redirect("core:employee_tasks")


@csrf_exempt
def telegram_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    message = payload.get("message") or {}
    text = message.get("text", "")
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    if not text.startswith("/start"):
        return HttpResponse(status=200)

    parts = text.split(maxsplit=1)
    token = parts[1].strip() if len(parts) > 1 else ""
    if not token:
        send_telegram_message(chat_id, "Ссылка приглашения не содержит код.")
        return HttpResponse(status=200)

    invite = InterviewTelegramInvite.objects.filter(token=token).select_related("interview").first()
    if not invite:
        send_telegram_message(chat_id, "Код приглашения недействителен.")
        return HttpResponse(status=200)

    invite.chat_id = chat_id
    invite.linked_at = timezone.now()
    invite.save(update_fields=["chat_id", "linked_at"])

    interview = invite.interview
    interview.candidate_telegram_chat_id = chat_id
    interview.save(update_fields=["candidate_telegram_chat_id"])

    # Если кандидат уже подтвержден админом до привязки Telegram,
    # выдаем новые временные учетные данные в чат сразу после привязки.
    if interview.status == "hired" and interview.employee_user:
        user = interview.employee_user
        temp_password = secrets.token_urlsafe(8)
        user.set_password(temp_password)
        user.save(update_fields=["password"])
        send_telegram_message(
            chat_id,
            (
                "Ваш Telegram успешно привязан.\n"
                "Вы подтверждены на работу в ООО 'Арт Кулинария'.\n"
                f"Логин: {user.username}\n"
                f"Временный пароль: {temp_password}\n"
                "После входа смените пароль."
            ),
        )
        return HttpResponse(status=200)

    send_telegram_message(
        chat_id,
        (
            f"Контакт для кандидата {interview.candidate_name} успешно привязан. "
            "После подтверждения администратором вы получите учетные данные."
        ),
    )
    return HttpResponse(status=200)
