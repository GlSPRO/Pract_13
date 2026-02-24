from django import forms
from django.contrib.auth.models import User

from core.models import EmployeeTask, EmployeeZoneAccess, JobPosition, UpskillDirective, ZONE_CHOICES
from hr_portal.models import InterviewRequest, ShiftAssignment


def _staff_queryset():
    return User.objects.filter(groups__name="Сотрудник", is_active=True).distinct().order_by("username")


def _staff_label(user: User) -> str:
    full_name = getattr(getattr(user, "profile", None), "full_name", "") or user.username
    return f"{full_name} ({user.username})"


class ShiftAssignmentCreateForm(forms.ModelForm):
    class Meta:
        model = ShiftAssignment
        fields = [
            "date",
            "start_time",
            "end_time",
            "workshop",
            "planned_staff",
            "assigned_staff",
            "assigned_employee",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        workshop = None
        workshop_key = self.add_prefix("workshop")
        if self.is_bound:
            workshop = self.data.get(workshop_key) or self.data.get("workshop")
        if not workshop:
            workshop = self.initial.get("workshop") or getattr(self.instance, "workshop", "")
        if not workshop and self.fields["workshop"].choices:
            workshop = self.fields["workshop"].choices[0][0]

        eligible_employees = _staff_queryset()
        if workshop:
            eligible_employees = eligible_employees.filter(
                zone_accesses__zone=workshop,
                zone_accesses__is_active=True,
            )
            self.fields["assigned_employee"].help_text = "В списке только сотрудники с допуском к выбранному цеху/участку."
        else:
            eligible_employees = eligible_employees.none()
            self.fields["assigned_employee"].help_text = "Сначала выберите цех/участок."

        self.fields["assigned_employee"].queryset = eligible_employees.distinct()
        self.fields["assigned_employee"].label_from_instance = _staff_label
        self.fields["date"].widget = forms.DateInput(attrs={"type": "date"})
        self.fields["start_time"].widget = forms.TimeInput(attrs={"type": "time"})
        self.fields["end_time"].widget = forms.TimeInput(attrs={"type": "time"})
        for field_name, field in self.fields.items():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.update({"class": css_class})

    def clean(self):
        cleaned = super().clean()
        employee = cleaned.get("assigned_employee")
        workshop = cleaned.get("workshop")
        if employee and workshop:
            has_access = EmployeeZoneAccess.objects.filter(
                employee=employee,
                zone=workshop,
                is_active=True,
            ).exists()
            if not has_access:
                self.add_error(
                    "assigned_employee",
                    f"Сотрудник не имеет допуска к зоне '{workshop}'. Назначьте повышение квалификации или допуск.",
                )
        return cleaned


class ShiftAssignmentReassignForm(forms.Form):
    assigned_employee = forms.ModelChoiceField(
        label="Ответственный сотрудник",
        queryset=User.objects.none(),
        required=False,
    )
    assigned_staff = forms.IntegerField(label="Назначено сотрудников", min_value=0)

    def __init__(self, *args, **kwargs):
        self.shift: ShiftAssignment = kwargs.pop("shift")
        super().__init__(*args, **kwargs)
        eligible_employees = _staff_queryset().filter(
            zone_accesses__zone=self.shift.workshop,
            zone_accesses__is_active=True,
        )
        self.fields["assigned_employee"].queryset = eligible_employees.distinct()
        self.fields["assigned_employee"].label_from_instance = _staff_label
        if self.shift.assigned_employee and self.fields["assigned_employee"].queryset.filter(
            pk=self.shift.assigned_employee.pk
        ).exists():
            self.fields["assigned_employee"].initial = self.shift.assigned_employee
        self.fields["assigned_staff"].initial = self.shift.assigned_staff
        for field_name, field in self.fields.items():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.update({"class": css_class})

    def save(self):
        self.shift.assigned_employee = self.cleaned_data["assigned_employee"]
        self.shift.assigned_staff = self.cleaned_data["assigned_staff"]
        if self.shift.assigned_employee and self.shift.assigned_staff == 0:
            # Если сотрудник выбран, минимум 1 сотрудник должен быть назначен.
            self.shift.assigned_staff = 1
        self.shift.save()
        return self.shift

    def clean(self):
        cleaned = super().clean()
        employee = cleaned.get("assigned_employee")
        if employee:
            has_access = EmployeeZoneAccess.objects.filter(
                employee=employee,
                zone=self.shift.workshop,
                is_active=True,
            ).exists()
            if not has_access:
                self.add_error(
                    "assigned_employee",
                    f"Сотрудник не имеет допуска к зоне '{self.shift.workshop}'.",
                )
        return cleaned


class InterviewCreateForm(forms.ModelForm):
    class Meta:
        model = InterviewRequest
        fields = [
            "candidate_name",
            "phone",
            "interview_at",
            "workshop",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["workshop"].widget = forms.Select(choices=ZONE_CHOICES)
        self.fields["workshop"].choices = ZONE_CHOICES
        self.fields["interview_at"].widget = forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        )
        self.fields["interview_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        for field_name, field in self.fields.items():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.update({"class": css_class})


class InterviewUpdateForm(forms.ModelForm):
    class Meta:
        model = InterviewRequest
        fields = [
            "interview_at",
            "workshop",
            "status",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["workshop"].widget = forms.Select(choices=ZONE_CHOICES)
        self.fields["workshop"].choices = ZONE_CHOICES
        self.fields["interview_at"].widget = forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        )
        self.fields["interview_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["status"].choices = [
            (InterviewRequest.STATUS_SCHEDULED, "Запланировано"),
            (InterviewRequest.STATUS_COMPLETED, "Проведено"),
            (InterviewRequest.STATUS_PENDING_APPROVAL, "На подтверждении"),
            (InterviewRequest.STATUS_REJECTED, "Отклонено"),
        ]
        for field_name, field in self.fields.items():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.update({"class": css_class})


class EmployeeTaskCreateForm(forms.ModelForm):
    class Meta:
        model = EmployeeTask
        fields = ["employee", "title", "description", "priority", "due_date", "status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = (
            User.objects.filter(groups__name="Сотрудник", is_active=True)
            .select_related("profile")
            .distinct()
            .order_by("username")
        )
        self.fields["employee"].label_from_instance = _staff_label
        self.fields["due_date"].widget = forms.DateInput(attrs={"type": "date"})
        self.fields["status"].initial = EmployeeTask.STATUS_NEW
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.update({"class": css_class})


class UpskillDirectiveCreateForm(forms.ModelForm):
    class Meta:
        model = UpskillDirective
        fields = ["employee", "target_zone", "target_level", "planned_date", "rationale"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = (
            User.objects.filter(groups__name="Сотрудник", is_active=True)
            .select_related("profile")
            .distinct()
            .order_by("username")
        )
        self.fields["employee"].label_from_instance = _staff_label
        self.fields["planned_date"].widget = forms.DateInput(attrs={"type": "date"})
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.update({"class": css_class})


class EmployeeProfileUpdateForm(forms.Form):
    full_name = forms.CharField(label="ФИО", max_length=255)
    position = forms.ModelChoiceField(
        label="Должность",
        queryset=JobPosition.objects.none(),
        required=False,
        empty_label="Выберите должность",
    )

    def __init__(self, *args, **kwargs):
        self.user_instance: User = kwargs.pop("user_instance")
        super().__init__(*args, **kwargs)
        profile = getattr(self.user_instance, "profile", None)
        self.fields["full_name"].initial = profile.full_name if profile else self.user_instance.username
        self.fields["position"].queryset = JobPosition.objects.filter(is_active=True).order_by("sort_order", "name")
        if profile and profile.position:
            position_obj = JobPosition.objects.filter(name=profile.position, is_active=True).first()
            if position_obj:
                self.fields["position"].initial = position_obj
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.update({"class": css_class})
