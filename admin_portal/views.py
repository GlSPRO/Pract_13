import json
import re
import secrets
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.core.paginator import EmptyPage, Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from admin_portal.forms import UserCreateForm, UserUpdateForm, ensure_group
from admin_portal.models import AuditLog
from admin_portal.utils import admin_required, is_admin
from core.telegram_utils import send_telegram_message
from core.models import Profile
from hr_portal.models import InterviewRequest

GROUP_CODES = {
    "admin": "Администратор",
    "hr": "HR",
    "staff": "Сотрудник",
}


class AdminLoginView(auth_views.LoginView):
    template_name = "admin_portal/login.html"
    redirect_authenticated_user = True
    extra_context = {"hide_shell": True}

    def form_valid(self, form):
        response = super().form_valid(form)
        # Проверяем право админа: если нет — сразу выходим и показываем сообщение
        if not is_admin(self.request.user):
            messages.error(self.request, "Нет доступа: требуется группа «Администратор».")
            from django.contrib.auth import logout

            logout(self.request)
            return redirect("admin_portal:login")
        AuditLog.objects.create(
            actor=self.request.user,
            action="login",
            object_type="user",
            object_id=str(self.request.user.pk),
            details="Успешный вход",
        )
        return response


class AdminLogoutView(LogoutView):
    """
    Django 5 по умолчанию разрешает только POST для logout.
    Разрешаем GET для удобства кнопки «Выход».
    """

    next_page = "admin_portal:login"
    http_method_names = ["get", "post", "options"]

    def get(self, request, *args, **kwargs):
        auth_logout(request)
        return redirect("admin_portal:login")

    def post(self, request, *args, **kwargs):
        auth_logout(request)
        return redirect("admin_portal:login")


def _status_meta(is_active: bool):
    if is_active:
        return {"status_text": "Активен", "status_color": "#2e9d6f"}
    return {"status_text": "Заблокирован", "status_color": "#c44536"}


def _paginate(queryset, request, per_page=10):
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get("page") or 1
    try:
        page_obj = paginator.page(page_number)
    except EmptyPage:
        page_obj = paginator.page(1)
    pages = []
    for num in paginator.page_range:
        pages.append(
            {"label": str(num), "url": f"{request.path}?page={num}", "is_active": num == page_obj.number, "disabled": False}
        )
    return page_obj, {
        "displayed": len(page_obj.object_list),
        "total": paginator.count,
        "pages": pages,
    }


def _build_replacements_trend(period: str):
    now = timezone.localtime()
    if period == "30d":
        days = 30
        slot_size = 7
        labels = ["1 нед", "2 нед", "3 нед", "4 нед", "5 нед"]
    else:
        days = 7
        slot_size = 1
        labels = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    start_dt = now - timedelta(days=days - 1)
    logs = AuditLog.objects.filter(
        action="update",
        created_at__gte=start_dt,
    ).filter(Q(details__icontains="переназнач") | Q(details__icontains="замен"))

    values = [0 for _ in labels]
    for log in logs:
        delta_days = (timezone.localtime(log.created_at).date() - start_dt.date()).days
        if delta_days < 0:
            continue
        slot_index = delta_days // slot_size
        if 0 <= slot_index < len(values):
            values[slot_index] += 1

    return {"labels": labels, "values": values}


def _generate_candidate_username(full_name: str, phone: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "", full_name.lower().replace(" ", ""))[:8]
    digits = "".join(ch for ch in phone if ch.isdigit())
    base = f"{slug or 'emp'}{digits[-4:] if digits else ''}"
    username = base or "emp"
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base}{counter}"
        counter += 1
    return username


@admin_required
def dashboard(request):
    users_qs = User.objects.all().select_related("profile").prefetch_related("groups")
    total = users_qs.count()
    active = users_qs.filter(is_active=True).count()
    locked = total - active

    group_overview = []
    for code, title in GROUP_CODES.items():
        group = Group.objects.filter(name=title).first()
        count = group.user_set.count() if group else 0
        active_count = group.user_set.filter(is_active=True).count() if group else 0
        group_overview.append({"name": title, "count": count, "active": active_count})

    recent_actions = AuditLog.objects.select_related("actor")[:5]
    recent_actions_ctx = [
        {
            "actor": log.actor.get_full_name() or log.actor.get_username() if log.actor else "—",
            "timestamp": log.created_at.strftime("%d.%m %H:%M"),
            "action": log.get_action_display(),
            "object": f"{log.object_type}:{log.object_id}",
        }
        for log in recent_actions
    ]

    dashboard_stats = [
        {"label": "Всего пользователей", "value": total, "subtitle": "Аккаунты портала", "delta": "", "icon": "bi-people"},
        {"label": "Активны", "value": active, "subtitle": "Могут войти", "delta": "", "icon": "bi-shield-check"},
        {"label": "Заблокированы", "value": locked, "subtitle": "Требуют разблокировки", "delta": "", "icon": "bi-lock"},
        {"label": "Группы", "value": len(GROUP_CODES), "subtitle": "RBAC роли", "delta": "", "icon": "bi-diagram-3"},
    ]

    reminders = [
        {"title": "Проверьте блокировки", "text": "Заблокированы только неактуальные учетные записи."},
        {"title": "Обновите роли", "text": "Перед запуском смен убедитесь, что группы назначены корректно."},
    ]

    period = request.GET.get("period", "7d")
    replacements_data = _build_replacements_trend(period)
    replacement_count = sum(replacements_data["values"])

    workshop_rows = [
        {"name": "Горячий цех", "planned": 14, "actual": 12},
        {"name": "Холодный цех", "planned": 10, "actual": 11},
        {"name": "Кондитерский участок", "planned": 8, "actual": 7},
        {"name": "Фасовка", "planned": 9, "actual": 9},
    ]
    for row in workshop_rows:
        row["delta"] = row["actual"] - row["planned"]
        row["load_ratio"] = round((row["actual"] / row["planned"]) * 100, 1) if row["planned"] else 0
        if row["delta"] < 0:
            row["status"] = "Недобор"
        elif row["delta"] > 0:
            row["status"] = "Перебор"
        else:
            row["status"] = "Норма"

    total_planned = sum(item["planned"] for item in workshop_rows)
    total_actual = sum(item["actual"] for item in workshop_rows)
    total_shortage = sum(abs(item["delta"]) for item in workshop_rows if item["delta"] < 0)
    total_excess = sum(item["delta"] for item in workshop_rows if item["delta"] > 0)
    global_load_ratio = round((total_actual / total_planned) * 100, 1) if total_planned else 0

    hourly_shortage = [
        {"hour": "06:00", "shortage": 1},
        {"hour": "08:00", "shortage": 3},
        {"hour": "10:00", "shortage": 2},
        {"hour": "12:00", "shortage": 4},
        {"hour": "14:00", "shortage": 3},
        {"hour": "16:00", "shortage": 2},
        {"hour": "18:00", "shortage": 1},
        {"hour": "20:00", "shortage": 0},
    ]
    peak_hour = max(hourly_shortage, key=lambda item: item["shortage"])

    load_chart_payload = {
        "labels": [row["name"] for row in workshop_rows],
        "planned": [row["planned"] for row in workshop_rows],
        "actual": [row["actual"] for row in workshop_rows],
    }
    shortage_chart_payload = {
        "labels": [row["hour"] for row in hourly_shortage],
        "shortage": [row["shortage"] for row in hourly_shortage],
    }
    replacements_chart_payload = {
        "labels": replacements_data["labels"],
        "values": replacements_data["values"],
    }

    context = {
        "hide_shell": False,
        "active_section": "dashboard",
        "dashboard_stats": dashboard_stats,
        "recent_actions": recent_actions_ctx,
        "group_overview": group_overview,
        "reminders": reminders,
        "shift_analytics_kpis": [
            {"label": "Недобор смен", "value": total_shortage, "suffix": "чел."},
            {"label": "Перебор смен", "value": total_excess, "suffix": "чел."},
            {"label": "Коэффициент загрузки", "value": global_load_ratio, "suffix": "%"},
            {"label": "Замен за период", "value": replacement_count, "suffix": "шт."},
        ],
        "workshop_rows": workshop_rows,
        "peak_hour": peak_hour,
        "period": period,
        "load_chart_json": json.dumps(load_chart_payload, ensure_ascii=False),
        "shortage_chart_json": json.dumps(shortage_chart_payload, ensure_ascii=False),
        "replacements_chart_json": json.dumps(replacements_chart_payload, ensure_ascii=False),
    }
    return render(request, "admin_portal/dashboard.html", context)


@admin_required
def users_list(request):
    q = (request.GET.get("q") or "").strip().lower()
    group_filter = request.GET.get("group")
    status_filter = request.GET.get("status")
    sort_key = request.GET.get("sort", "username")

    users_qs = User.objects.all().select_related("profile").prefetch_related("groups")
    if q:
        users_qs = users_qs.filter(Q(username__icontains=q) | Q(profile__full_name__icontains=q))
    if group_filter in GROUP_CODES:
        group = ensure_group(group_filter)
        if group:
            users_qs = users_qs.filter(groups=group)
    if status_filter == "active":
        users_qs = users_qs.filter(is_active=True)
    elif status_filter == "locked":
        users_qs = users_qs.filter(is_active=False)

    allowed_sorts = {"username", "profile__full_name", "is_active"}
    order_map = {
        "username": "username",
        "full_name": "profile__full_name",
        "role": "groups__name",
    }
    if sort_key in {"username", "full_name", "role"}:
        users_qs = users_qs.order_by(order_map.get(sort_key, "username"))

    page_obj, page_info = _paginate(users_qs, request, per_page=8)

    items = []
    for user in page_obj.object_list:
        profile = getattr(user, "profile", None)
        full_name = profile.full_name if profile else ""
        group = user.groups.first()
        role = group.name if group else "—"
        items.append(
            {
                "id": user.id,
                "username": user.username,
                "full_name": full_name,
                "role": role,
                "is_active": user.is_active,
                **_status_meta(user.is_active),
            }
        )

    context = {
        "hide_shell": False,
        "active_section": "users",
        "users": items,
        "current_sort": sort_key,
        "group_filters": [{"code": k, "title": v} for k, v in GROUP_CODES.items()],
        "page_info": page_info,
    }
    return render(request, "admin_portal/users_list.html", context)


@admin_required
@transaction.atomic
def user_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user, password = form.save(actor=request.user)
            AuditLog.objects.create(
                actor=request.user,
                action="create",
                object_type="user",
                object_id=str(user.pk),
                details=f"Создан пользователь {user.username} ({password})",
            )
            messages.success(request, f"Пользователь {user.username} создан. Пароль показан один раз: {password}")
            return redirect("admin_portal:users_list")
    else:
        form = UserCreateForm()

    context = {
        "hide_shell": False,
        "active_section": "users",
        "mode": "create",
        "form": form,
        "user_data": {
            "username": form["username"].value() or "",
            "full_name": form["full_name"].value() or "",
            "group": form["group"].value() or "",
            "status": "active",
            "password": getattr(form, "generated_password", ""),
        },
        "groups": [{"code": k, "title": v} for k, v in GROUP_CODES.items()],
    }
    return render(request, "admin_portal/user_form.html", context)


@admin_required
@transaction.atomic
def user_edit(request, user_id: int):
    user_instance = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        form = UserUpdateForm(request.POST, user_instance=user_instance)
        if form.is_valid():
            form.save(actor=request.user)
            AuditLog.objects.create(
                actor=request.user,
                action="update",
                object_type="user",
                object_id=str(user_instance.pk),
                details="Обновлены данные пользователя",
            )
            messages.success(request, "Изменения сохранены.")
            return redirect("admin_portal:users_list")
    else:
        form = UserUpdateForm(user_instance=user_instance)

    profile = getattr(user_instance, "profile", None)
    full_name = profile.full_name if profile else ""
    group = user_instance.groups.first()
    back_map = {"Администратор": "admin", "HR": "hr", "Сотрудник": "staff"}

    context = {
        "hide_shell": False,
        "active_section": "users",
        "mode": "edit",
        "form": form,
        "user_data": {
            "username": user_instance.username,
            "full_name": full_name,
            "group": back_map.get(group.name) if group else "",
            "status": "active" if user_instance.is_active else "locked",
        },
        "groups": [{"code": k, "title": v} for k, v in GROUP_CODES.items()],
    }
    return render(request, "admin_portal/user_form.html", context)


@admin_required
@transaction.atomic
def user_lock(request, user_id: int):
    user_instance = get_object_or_404(User, pk=user_id)
    user_data = {
        "username": user_instance.username,
        "full_name": getattr(user_instance.profile, "full_name", ""),
        **_status_meta(user_instance.is_active),
    }
    if request.method == "POST":
        user_instance.is_active = False
        user_instance.save()
        AuditLog.objects.create(
            actor=request.user,
            action="lock",
            object_type="user",
            object_id=str(user_instance.pk),
            details="Пользователь заблокирован",
        )
        messages.warning(request, "Пользователь заблокирован.")
        return redirect("admin_portal:users_list")

    context = {
        "hide_shell": False,
        "active_section": "users",
        "action": "lock",
        "user_data": user_data,
    }
    return render(request, "admin_portal/user_lock_confirm.html", context)


@admin_required
@transaction.atomic
def user_unlock(request, user_id: int):
    user_instance = get_object_or_404(User, pk=user_id)
    user_data = {
        "username": user_instance.username,
        "full_name": getattr(user_instance.profile, "full_name", ""),
        **_status_meta(user_instance.is_active),
    }
    if request.method == "POST":
        user_instance.is_active = True
        user_instance.save()
        AuditLog.objects.create(
            actor=request.user,
            action="unlock",
            object_type="user",
            object_id=str(user_instance.pk),
            details="Пользователь разблокирован",
        )
        messages.success(request, "Пользователь разблокирован.")
        return redirect("admin_portal:users_list")

    context = {
        "hide_shell": False,
        "active_section": "users",
        "action": "unlock",
        "user_data": user_data,
    }
    return render(request, "admin_portal/user_lock_confirm.html", context)


@admin_required
def audit_log(request):
    audit_qs = AuditLog.objects.select_related("actor")

    actor_filter = request.GET.get("actor", "").strip()
    action_filter = request.GET.get("action")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if actor_filter:
        audit_qs = audit_qs.filter(
            Q(actor__username__icontains=actor_filter)
            | Q(actor__first_name__icontains=actor_filter)
            | Q(actor__last_name__icontains=actor_filter)
        )
    if action_filter:
        audit_qs = audit_qs.filter(action=action_filter)
    if date_from:
        audit_qs = audit_qs.filter(created_at__date__gte=date_from)
    if date_to:
        audit_qs = audit_qs.filter(created_at__date__lte=date_to)

    page_obj, audit_info = _paginate(audit_qs, request, per_page=12)

    audit_rows = [
        {
            "date": log.created_at.strftime("%d.%m.%Y %H:%M"),
            "actor": log.actor.get_full_name() or log.actor.get_username() if log.actor else "—",
            "action": log.get_action_display(),
            "object": f"{log.object_type}: {log.object_id}",
            "details": log.details,
        }
        for log in page_obj.object_list
    ]

    action_filters = AuditLog.ACTION_CHOICES

    context = {
        "hide_shell": False,
        "active_section": "audit",
        "audit_rows": audit_rows,
        "audit_info": audit_info,
        "action_filters": action_filters,
    }
    return render(request, "admin_portal/audit_list.html", context)


@admin_required
def interview_approvals(request):
    items = InterviewRequest.objects.select_related("hr_manager").order_by("-interview_at")
    context = {
        "hide_shell": False,
        "active_section": "interviews",
        "interviews": items,
        "pending_count": items.filter(status=InterviewRequest.STATUS_PENDING_APPROVAL).count(),
    }
    return render(request, "admin_portal/interview_approvals.html", context)


@admin_required
@transaction.atomic
def interview_approve(request, interview_id: int):
    interview = get_object_or_404(InterviewRequest, pk=interview_id)
    if request.method == "POST":
        if interview.status != InterviewRequest.STATUS_PENDING_APPROVAL:
            messages.error(request, "Можно подтверждать только заявки со статусом 'На подтверждении'.")
            return redirect("admin_portal:interview_approvals")

        employee_group, _ = Group.objects.get_or_create(name="Сотрудник")
        username = _generate_candidate_username(interview.candidate_name, interview.phone)
        password = secrets.token_urlsafe(8)
        user = User.objects.create(username=username, is_active=True)
        user.set_password(password)
        user.groups.set([employee_group])
        user.save()
        Profile.objects.update_or_create(
            user=user,
            defaults={
                "full_name": interview.candidate_name,
                "position": "Сотрудник производства",
                "telegram_chat_id": interview.candidate_telegram_chat_id,
            },
        )

        interview.status = InterviewRequest.STATUS_HIRED
        interview.approved_by = request.user
        interview.employee_user = user
        interview.save(update_fields=["status", "approved_by", "employee_user", "updated_at"])

        AuditLog.objects.create(
            actor=request.user,
            action="create",
            object_type="user",
            object_id=str(user.pk),
            details=(
                f"Подтвержден кандидат {interview.candidate_name}. "
                f"Создана учетная запись: {username} / {password}"
            ),
        )
        messages.success(
            request,
            (
                f"Кандидат подтвержден. Учетка создана: {username}. "
                f"Пароль (показать один раз): {password}. "
                "Сотрудник уже доступен HR в графике смен для назначения."
            ),
        )
        if interview.candidate_telegram_chat_id:
            send_telegram_message(
                interview.candidate_telegram_chat_id,
                (
                    "Вас подтвердили на работу в ООО 'Арт Кулинария'.\n"
                    f"Логин: {username}\n"
                    f"Пароль: {password}\n"
                    "После входа рекомендуем сменить пароль."
                ),
            )
        else:
            messages.warning(
                request,
                "Telegram кандидата пока не привязан. После привязки в боте ему будут выданы временные учетные данные.",
            )
        return redirect("admin_portal:interview_approvals")

    context = {
        "hide_shell": False,
        "active_section": "interviews",
        "interview": interview,
    }
    return render(request, "admin_portal/interview_approve_confirm.html", context)
