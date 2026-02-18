from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def is_admin(user) -> bool:
    return user.is_superuser or user.groups.filter(name="Администратор").exists()


def is_hr(user) -> bool:
    if not user.is_authenticated:
        return False
    return user.groups.filter(name="HR").exists()


def is_employee(user) -> bool:
    if not user.is_authenticated:
        return False
    return user.groups.filter(name="Сотрудник").exists()


def admin_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not is_admin(request.user):
            raise PermissionDenied("Требуется группа «Администратор».")
        return view_func(request, *args, **kwargs)

    return _wrapped


def hr_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("hr_portal:login")
        if not is_hr(request.user):
            raise PermissionDenied("Требуется группа «HR».")
        return view_func(request, *args, **kwargs)

    return _wrapped


def employee_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("core:login")
        if not is_employee(request.user):
            raise PermissionDenied("Требуется роль «Сотрудник».")
        return view_func(request, *args, **kwargs)

    return _wrapped
