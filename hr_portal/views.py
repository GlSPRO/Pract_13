import secrets

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth import logout
from django.contrib.auth.models import User
from django.contrib.auth.views import LogoutView
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from admin_portal.models import AuditLog
from admin_portal.utils import hr_required, is_hr
from core.telegram_utils import build_start_link
from core.models import (
    EmployeeTask,
    EmployeeZoneAccess,
    LeaveRequest,
    Profile,
    ProfileChangeRequest,
    UpskillDirective,
)
from hr_portal.forms import (
    EmployeeTaskCreateForm,
    EmployeeProfileUpdateForm,
    InterviewCreateForm,
    InterviewUpdateForm,
    ShiftAssignmentCreateForm,
    ShiftAssignmentReassignForm,
    UpskillDirectiveCreateForm,
)
from hr_portal.models import HiringRequest, InterviewRequest, InterviewTelegramInvite, ShiftAssignment


class HRLoginView(auth_views.LoginView):
    template_name = "hr_portal/login.html"
    redirect_authenticated_user = True
    extra_context = {"hide_shell": True, "portal_type": "hr"}

    def get_success_url(self):
        return "/hr/dashboard/"

    def form_valid(self, form):
        response = super().form_valid(form)
        if not is_hr(self.request.user):
            messages.error(self.request, "Нет доступа: требуется группа «HR».")
            logout(self.request)
            return redirect("hr_portal:login")
        AuditLog.objects.create(
            actor=self.request.user,
            action="login",
            object_type="hr_portal",
            object_id=str(self.request.user.pk),
            details="Успешный вход в HR-портал",
        )
        return response


class HRLogoutView(LogoutView):
    next_page = "hr_portal:login"
    http_method_names = ["get", "post", "options"]

    def get(self, request, *args, **kwargs):
        logout(request)
        return redirect("hr_portal:login")

    def post(self, request, *args, **kwargs):
        logout(request)
        return redirect("hr_portal:login")


@hr_required
def dashboard(request):
    total_staff = User.objects.filter(groups__name="Сотрудник").distinct().count()
    active_staff = User.objects.filter(groups__name="Сотрудник", is_active=True).distinct().count()
    hr_count = User.objects.filter(groups__name="HR").distinct().count()
    today = timezone.localdate()
    horizon = today + timezone.timedelta(days=6)
    shifts = ShiftAssignment.objects.filter(date__gte=today, date__lte=horizon).order_by("date", "start_time")
    open_positions = sum(max(0, shift.planned_staff - shift.assigned_staff) for shift in shifts)

    workshops = {}
    for shift in shifts:
        if shift.workshop not in workshops:
            workshops[shift.workshop] = {"name": shift.workshop, "planned": 0, "actual": 0}
        workshops[shift.workshop]["planned"] += shift.planned_staff
        workshops[shift.workshop]["actual"] += shift.assigned_staff
    staff_by_workshop = list(workshops.values())
    for row in staff_by_workshop:
        row["ratio"] = round((row["actual"] / row["planned"]) * 100, 1) if row["planned"] else 0

    recent_hr_actions = (
        AuditLog.objects.select_related("actor")
        .filter(Q(object_type__icontains="shift") | Q(details__icontains="смен"))
        .order_by("-created_at")[:6]
    )
    recent_actions = [
        {
            "actor": log.actor.get_full_name() or log.actor.username if log.actor else "—",
            "date": log.created_at.strftime("%d.%m %H:%M"),
            "action": log.get_action_display(),
            "details": log.details,
        }
        for log in recent_hr_actions
    ]

    context = {
        "hide_shell": False,
        "portal_type": "hr",
        "active_section": "dashboard",
        "kpi_cards": [
            {"label": "Сотрудники", "value": total_staff, "hint": "Всего в штате"},
            {"label": "Активные", "value": active_staff, "hint": "Допущены к сменам"},
            {"label": "HR менеджеры", "value": hr_count, "hint": "Пользователи роли HR"},
            {"label": "Открытые позиции", "value": open_positions, "hint": "Требуется подбор"},
            {
                "label": "Собеседования на подтверждении",
                "value": InterviewRequest.objects.filter(status=InterviewRequest.STATUS_PENDING_APPROVAL).count(),
                "hint": "Ждут решения администратора",
            },
        ],
        "staff_by_workshop": staff_by_workshop,
        "recent_actions": recent_actions,
    }
    return render(request, "hr_portal/dashboard.html", context)


@hr_required
def employees(request):
    q = (request.GET.get("q") or "").strip()
    users_qs = User.objects.filter(groups__name="Сотрудник").select_related("profile").distinct()
    if q:
        users_qs = users_qs.filter(Q(username__icontains=q) | Q(profile__full_name__icontains=q))
    users_qs = users_qs.order_by("username")

    employees_list = []
    for user in users_qs:
        profile = getattr(user, "profile", None)
        access_list = list(
            user.zone_accesses.filter(is_active=True).values_list("zone", flat=True)
        )
        employees_list.append(
            {
                "id": user.id,
                "username": user.username,
                "full_name": profile.full_name if profile else user.username,
                "position": profile.position if profile and profile.position else "Не указана",
                "status": "Активен" if user.is_active else "Заблокирован",
                "zones": ", ".join(access_list) if access_list else "Нет допуска",
            }
        )

    context = {
        "hide_shell": False,
        "portal_type": "hr",
        "active_section": "employees",
        "employees": employees_list,
    }
    return render(request, "hr_portal/employees.html", context)


@hr_required
def employee_edit(request, user_id: int):
    user_instance = get_object_or_404(
        User.objects.filter(groups__name="Сотрудник").select_related("profile").distinct(),
        pk=user_id,
    )

    if request.method == "POST":
        form = EmployeeProfileUpdateForm(request.POST, user_instance=user_instance)
        if form.is_valid():
            profile, _ = Profile.objects.get_or_create(
                user=user_instance,
                defaults={"full_name": user_instance.username, "position": ""},
            )
            profile.full_name = form.cleaned_data["full_name"]
            selected_position = form.cleaned_data["position"]
            profile.position = selected_position.name if selected_position else ""
            profile.save(update_fields=["full_name", "position"])
            AuditLog.objects.create(
                actor=request.user,
                action="update",
                object_type="employee_profile",
                object_id=str(user_instance.pk),
                details=f"HR обновил профиль сотрудника {user_instance.username}",
            )
            messages.success(request, "Данные сотрудника сохранены.")
            return redirect("hr_portal:employees")
    else:
        form = EmployeeProfileUpdateForm(user_instance=user_instance)

    context = {
        "hide_shell": False,
        "portal_type": "hr",
        "active_section": "employees",
        "form": form,
        "employee_user": user_instance,
    }
    return render(request, "hr_portal/employee_edit.html", context)


@hr_required
def qualification_control(request):
    status_filter = request.GET.get("status")
    employee_filter = request.GET.get("employee")
    qs = UpskillDirective.objects.select_related("employee", "employee__profile", "created_by")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if employee_filter:
        qs = qs.filter(employee__username__icontains=employee_filter)
    context = {
        "hide_shell": False,
        "portal_type": "hr",
        "active_section": "qualification",
        "items": qs.order_by("-created_at"),
        "status_choices": UpskillDirective.STATUS_CHOICES,
        "current_status": status_filter or "",
    }
    return render(request, "hr_portal/qualification_control.html", context)


@hr_required
def qualification_create(request):
    if request.method == "POST":
        form = UpskillDirectiveCreateForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.created_by = request.user
            item.status = UpskillDirective.STATUS_ASSIGNED
            item.save()
            AuditLog.objects.create(
                actor=request.user,
                action="create",
                object_type="upskill_directive",
                object_id=str(item.pk),
                details=f"Назначено повышение квалификации {item.employee.username} -> {item.target_zone}",
            )
            messages.success(request, "Назначение на повышение квалификации создано.")
            return redirect("hr_portal:qualification_control")
    else:
        form = UpskillDirectiveCreateForm()

    context = {
        "hide_shell": False,
        "portal_type": "hr",
        "active_section": "qualification",
        "form": form,
    }
    return render(request, "hr_portal/qualification_form.html", context)


@hr_required
def qualification_set_status(request, item_id: int, decision: str):
    item = get_object_or_404(UpskillDirective, pk=item_id)
    if request.method == "POST":
        if decision == "in_progress":
            item.status = UpskillDirective.STATUS_IN_PROGRESS
            messages.info(request, "Статус переведен в 'В обучении'.")
        elif decision == "approve":
            if not item.employee_certificate:
                messages.error(request, "Нельзя подтвердить допуск без загруженного сертификата сотрудника.")
                return redirect("hr_portal:qualification_control")
            item.status = UpskillDirective.STATUS_APPROVED
            access, _ = EmployeeZoneAccess.objects.get_or_create(
                employee=item.employee,
                zone=item.target_zone,
                defaults={
                    "qualification_level": item.target_level,
                    "is_active": True,
                    "granted_by": request.user,
                },
            )
            access.qualification_level = item.target_level
            access.is_active = True
            access.granted_by = request.user
            access.save()
            messages.success(request, "Квалификация подтверждена. Допуск к зоне выдан.")
        elif decision == "reject":
            item.status = UpskillDirective.STATUS_REJECTED
            messages.warning(request, "Повышение квалификации отклонено.")
        item.hr_comment = request.POST.get("hr_comment", "").strip()
        item.save(update_fields=["status", "hr_comment", "updated_at"])
        AuditLog.objects.create(
            actor=request.user,
            action="update",
            object_type="upskill_directive",
            object_id=str(item.pk),
            details=f"HR {decision}: {item.employee.username} / {item.target_zone}",
        )
    return redirect("hr_portal:qualification_control")


@hr_required
def profile_requests(request):
    status_filter = request.GET.get("status")
    qs = ProfileChangeRequest.objects.select_related("employee", "employee__profile")
    if status_filter:
        qs = qs.filter(status=status_filter)
    context = {
        "hide_shell": False,
        "portal_type": "hr",
        "active_section": "requests_profile",
        "requests_list": qs.order_by("-created_at"),
        "status_choices": ProfileChangeRequest.STATUS_CHOICES,
        "current_status": status_filter or "",
    }
    return render(request, "hr_portal/profile_requests.html", context)


@hr_required
def profile_request_decision(request, request_id: int, decision: str):
    item = get_object_or_404(ProfileChangeRequest.objects.select_related("employee", "employee__profile"), pk=request_id)
    if request.method == "POST":
        if decision == "approve":
            item.status = ProfileChangeRequest.STATUS_APPROVED
            profile, _ = Profile.objects.get_or_create(
                user=item.employee,
                defaults={"full_name": item.employee.username, "position": "Сотрудник"},
            )
            label = item.field_label.lower()
            if "фио" in label or "имя" in label:
                profile.full_name = item.new_value
                profile.save(update_fields=["full_name"])
            if "долж" in label:
                profile.position = item.new_value
                profile.save(update_fields=["position"])
            messages.success(request, "Заявка сотрудника подтверждена.")
        else:
            item.status = ProfileChangeRequest.STATUS_REJECTED
            messages.warning(request, "Заявка сотрудника отклонена.")
        item.save(update_fields=["status"])
        AuditLog.objects.create(
            actor=request.user,
            action="update",
            object_type="profile_change_request",
            object_id=str(item.pk),
            details=f"HR {decision}: {item.employee.username} / {item.field_label}",
        )
    return redirect("hr_portal:profile_requests")


@hr_required
def leave_requests(request):
    status_filter = request.GET.get("status")
    type_filter = request.GET.get("type")
    qs = LeaveRequest.objects.select_related("employee", "employee__profile")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if type_filter:
        qs = qs.filter(leave_type=type_filter)
    context = {
        "hide_shell": False,
        "portal_type": "hr",
        "active_section": "requests_leave",
        "leave_list": qs.order_by("-created_at"),
        "status_choices": LeaveRequest.STATUS_CHOICES,
        "type_choices": LeaveRequest.TYPE_CHOICES,
        "current_status": status_filter or "",
        "current_type": type_filter or "",
    }
    return render(request, "hr_portal/leave_requests.html", context)


@hr_required
def leave_request_decision(request, leave_id: int, decision: str):
    item = get_object_or_404(LeaveRequest, pk=leave_id)
    if request.method == "POST":
        if decision == "approve":
            item.status = LeaveRequest.STATUS_APPROVED
            messages.success(request, "Заявка на отпуск/больничный подтверждена.")
        else:
            item.status = LeaveRequest.STATUS_REJECTED
            messages.warning(request, "Заявка на отпуск/больничный отклонена.")
        item.save(update_fields=["status"])
        AuditLog.objects.create(
            actor=request.user,
            action="update",
            object_type="leave_request",
            object_id=str(item.pk),
            details=f"HR {decision}: {item.employee.username} / {item.get_leave_type_display()}",
        )
    return redirect("hr_portal:leave_requests")


@hr_required
def task_control(request):
    status_filter = request.GET.get("status")
    employee_filter = request.GET.get("employee")
    priority_filter = request.GET.get("priority")
    qs = EmployeeTask.objects.select_related("employee", "employee__profile")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if employee_filter:
        qs = qs.filter(employee__username__icontains=employee_filter)
    if priority_filter:
        qs = qs.filter(priority=priority_filter)
    context = {
        "hide_shell": False,
        "portal_type": "hr",
        "active_section": "tasks_control",
        "tasks": qs.order_by("status", "due_date", "-updated_at"),
        "status_choices": EmployeeTask.STATUS_CHOICES,
        "priority_choices": EmployeeTask.PRIORITY_CHOICES,
        "current_status": status_filter or "",
        "current_priority": priority_filter or "",
    }
    return render(request, "hr_portal/task_control.html", context)


@hr_required
def task_set_status(request, task_id: int):
    task = get_object_or_404(EmployeeTask, pk=task_id)
    if request.method == "POST":
        new_status = request.POST.get("status")
        allowed = {code for code, _ in EmployeeTask.STATUS_CHOICES}
        if new_status in allowed:
            task.status = new_status
            task.save(update_fields=["status", "updated_at"])
            AuditLog.objects.create(
                actor=request.user,
                action="update",
                object_type="employee_task",
                object_id=str(task.pk),
                details=f"HR изменил статус задачи {task.employee.username} -> {task.get_status_display()}",
            )
            messages.success(request, "Статус задачи обновлен.")
    return redirect("hr_portal:task_control")


@hr_required
def task_create(request):
    if request.method == "POST":
        form = EmployeeTaskCreateForm(request.POST)
        if form.is_valid():
            task = form.save()
            AuditLog.objects.create(
                actor=request.user,
                action="create",
                object_type="employee_task",
                object_id=str(task.pk),
                details=f"HR поставил задачу {task.employee.username}: {task.title}",
            )
            messages.success(request, "Задача сотруднику создана.")
            return redirect("hr_portal:task_control")
    else:
        form = EmployeeTaskCreateForm()

    context = {
        "hide_shell": False,
        "portal_type": "hr",
        "active_section": "tasks_control",
        "form": form,
    }
    return render(request, "hr_portal/task_create.html", context)


@hr_required
def interviews(request):
    status_filter = request.GET.get("status")
    q = (request.GET.get("q") or "").strip()
    interview_qs = InterviewRequest.objects.select_related("hr_manager", "employee_user", "telegram_invite")
    if status_filter:
        interview_qs = interview_qs.filter(status=status_filter)
    if q:
        interview_qs = interview_qs.filter(Q(candidate_name__icontains=q) | Q(phone__icontains=q))

    rows = []
    for item in interview_qs.order_by("-interview_at"):
        invite = getattr(item, "telegram_invite", None)
        rows.append(
            {
                "id": item.id,
                "candidate_name": item.candidate_name,
                "phone": item.phone,
                "interview_at": item.interview_at,
                "workshop": item.workshop,
                "status": item.status,
                "status_label": item.get_status_display(),
                "telegram_chat_id": item.candidate_telegram_chat_id,
                "telegram_link": build_start_link(invite.token) if invite else "",
            }
        )

    context = {
        "hide_shell": False,
        "portal_type": "hr",
        "active_section": "interviews",
        "interviews": rows,
        "hiring_recommendations": HiringRequest.objects.exclude(status=HiringRequest.STATUS_CLOSED)
        .select_related("created_by")
        .order_by("status", "-created_at")[:8],
        "status_choices": InterviewRequest.STATUS_CHOICES,
        "current_status": status_filter or "",
    }
    return render(request, "hr_portal/interviews_list.html", context)


@hr_required
def interview_create(request):
    if request.method == "POST":
        form = InterviewCreateForm(request.POST)
        if form.is_valid():
            interview = form.save(commit=False)
            interview.hr_manager = request.user
            interview.status = InterviewRequest.STATUS_SCHEDULED
            interview.save()
            AuditLog.objects.create(
                actor=request.user,
                action="create",
                object_type="interview",
                object_id=str(interview.pk),
                details=f"Создано собеседование: {interview.candidate_name}, {interview.phone}",
            )
            messages.success(request, "Собеседование запланировано.")
            return redirect("hr_portal:interviews")
    else:
        form = InterviewCreateForm()

    context = {
        "hide_shell": False,
        "portal_type": "hr",
        "active_section": "interviews",
        "form": form,
        "mode": "create",
    }
    return render(request, "hr_portal/interview_form.html", context)


@hr_required
def interview_edit(request, interview_id: int):
    interview = get_object_or_404(InterviewRequest, pk=interview_id)
    if request.method == "POST":
        form = InterviewUpdateForm(request.POST, instance=interview)
        if form.is_valid():
            updated = form.save()
            AuditLog.objects.create(
                actor=request.user,
                action="update",
                object_type="interview",
                object_id=str(updated.pk),
                details=f"Обновлено собеседование: {updated.candidate_name}, статус={updated.get_status_display()}",
            )
            messages.success(request, "Карточка собеседования обновлена.")
            return redirect("hr_portal:interviews")
    else:
        form = InterviewUpdateForm(instance=interview)

    context = {
        "hide_shell": False,
        "portal_type": "hr",
        "active_section": "interviews",
        "form": form,
        "mode": "edit",
        "interview": interview,
    }
    return render(request, "hr_portal/interview_form.html", context)


@hr_required
def interview_send_to_admin(request, interview_id: int):
    interview = get_object_or_404(InterviewRequest, pk=interview_id)
    if request.method == "POST":
        interview.status = InterviewRequest.STATUS_PENDING_APPROVAL
        interview.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(
            actor=request.user,
            action="update",
            object_type="interview",
            object_id=str(interview.pk),
            details=f"Кандидат отправлен на подтверждение администратору: {interview.candidate_name}",
        )
        messages.success(request, "Кандидат отправлен администратору на подтверждение.")
        return redirect("hr_portal:interviews")

    context = {
        "hide_shell": False,
        "portal_type": "hr",
        "active_section": "interviews",
        "interview": interview,
    }
    return render(request, "hr_portal/interview_send_confirm.html", context)


@hr_required
def interview_telegram_link(request, interview_id: int):
    interview = get_object_or_404(InterviewRequest, pk=interview_id)
    invite, created = InterviewTelegramInvite.objects.get_or_create(
        interview=interview,
        defaults={"token": secrets.token_urlsafe(24)},
    )
    if not created:
        invite.token = secrets.token_urlsafe(24)
        invite.chat_id = ""
        invite.linked_at = None
        invite.save(update_fields=["token", "chat_id", "linked_at"])
        interview.candidate_telegram_chat_id = ""
        interview.save(update_fields=["candidate_telegram_chat_id"])

    link = build_start_link(invite.token)
    if not link:
        messages.error(request, "Не задан TELEGRAM_BOT_USERNAME. Невозможно сформировать ссылку.")
    else:
        messages.info(request, f"Ссылка для кандидата: {link}")
    return redirect("hr_portal:interviews")


@hr_required
def schedule(request):
    schedule_rows = []
    for shift in ShiftAssignment.objects.select_related("assigned_employee").order_by("date", "start_time", "workshop"):
        schedule_rows.append(
            {
                "id": shift.id,
                "date": f"{shift.date.strftime('%d.%m.%Y')}, {shift.start_time.strftime('%H:%M')}-{shift.end_time.strftime('%H:%M')}",
                "workshop": shift.workshop,
                "planned": shift.planned_staff,
                "assigned": shift.assigned_staff,
                "employee": shift.assigned_employee.profile.full_name
                if shift.assigned_employee and hasattr(shift.assigned_employee, "profile")
                else (shift.assigned_employee.username if shift.assigned_employee else "Не назначен"),
            }
        )
    for row in schedule_rows:
        row["delta"] = row["assigned"] - row["planned"]
        if row["delta"] < 0:
            row["status"] = "Недобор"
        elif row["delta"] > 0:
            row["status"] = "Перебор"
        else:
            row["status"] = "Норма"

    assignable_employees = (
        User.objects.filter(groups__name="Сотрудник", is_active=True)
        .select_related("profile")
        .distinct()
        .order_by("-profile__created_at", "username")
    )
    assignable = []
    for user in assignable_employees:
        profile = getattr(user, "profile", None)
        assignable.append(
            {
                "full_name": profile.full_name if profile and profile.full_name else user.username,
                "username": user.username,
                "created_at": profile.created_at if profile else None,
            }
        )

    context = {
        "hide_shell": False,
        "portal_type": "hr",
        "active_section": "schedule",
        "schedule_rows": schedule_rows,
        "assignable_employees": assignable[:8],
    }
    return render(request, "hr_portal/schedule.html", context)


@hr_required
def schedule_create(request):
    if request.method == "POST":
        form = ShiftAssignmentCreateForm(request.POST)
        if form.is_valid():
            shift = form.save()
            AuditLog.objects.create(
                actor=request.user,
                action="create",
                object_type="shift_assignment",
                object_id=str(shift.pk),
                details=f"Создана смена: {shift.workshop} {shift.date} {shift.start_time.strftime('%H:%M')}",
            )
            messages.success(request, "Смена добавлена в график.")
            return redirect("hr_portal:schedule")
    else:
        form = ShiftAssignmentCreateForm()

    context = {
        "hide_shell": False,
        "portal_type": "hr",
        "active_section": "schedule",
        "form": form,
        "mode": "create",
    }
    return render(request, "hr_portal/schedule_form.html", context)


@hr_required
def schedule_reassign(request, shift_id: int):
    shift = get_object_or_404(ShiftAssignment.objects.select_related("assigned_employee"), pk=shift_id)
    old_employee = shift.assigned_employee.username if shift.assigned_employee else "не назначен"

    if request.method == "POST":
        form = ShiftAssignmentReassignForm(request.POST, shift=shift)
        if form.is_valid():
            updated_shift = form.save()
            new_employee = updated_shift.assigned_employee.username if updated_shift.assigned_employee else "не назначен"
            AuditLog.objects.create(
                actor=request.user,
                action="update",
                object_type="shift_assignment",
                object_id=str(updated_shift.pk),
                details=(
                    f"Переназначение смены: {updated_shift.workshop} "
                    f"{updated_shift.date} {updated_shift.start_time.strftime('%H:%M')} "
                    f"{old_employee} -> {new_employee}"
                ),
            )
            messages.success(request, "Смена переназначена.")
            return redirect("hr_portal:schedule")
    else:
        form = ShiftAssignmentReassignForm(shift=shift)

    context = {
        "hide_shell": False,
        "portal_type": "hr",
        "active_section": "schedule",
        "form": form,
        "mode": "reassign",
        "shift": shift,
    }
    return render(request, "hr_portal/schedule_form.html", context)
