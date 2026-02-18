from django import forms
from django.contrib.auth.models import User

from core.models import EmployeeTask
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
        self.fields["assigned_employee"].queryset = _staff_queryset()
        self.fields["assigned_employee"].label_from_instance = _staff_label
        self.fields["date"].widget = forms.DateInput(attrs={"type": "date"})
        self.fields["start_time"].widget = forms.TimeInput(attrs={"type": "time"})
        self.fields["end_time"].widget = forms.TimeInput(attrs={"type": "time"})
        for field_name, field in self.fields.items():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.update({"class": css_class})


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
        self.fields["assigned_employee"].queryset = _staff_queryset()
        self.fields["assigned_employee"].label_from_instance = _staff_label
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
