from django import forms

from core.models import LeaveRequest, ProfileChangeRequest


class ProfileChangeRequestForm(forms.ModelForm):
    class Meta:
        model = ProfileChangeRequest
        fields = ["field_label", "new_value"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control"})


class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ["leave_type", "start_date", "end_date", "document_name", "note"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_date"].widget = forms.DateInput(attrs={"type": "date"})
        self.fields["end_date"].widget = forms.DateInput(attrs={"type": "date"})
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.update({"class": css_class})


class EmployeeQualificationConfirmForm(forms.Form):
    employee_comment = forms.CharField(
        label="Комментарий о прохождении",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Кратко: где и когда прошли обучение"}),
    )
    employee_certificate = forms.FileField(
        label="Сертификат о повышении квалификации",
        required=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee_comment"].widget.attrs.update({"class": "form-control form-control-sm"})
        self.fields["employee_certificate"].widget.attrs.update(
            {
                "class": "form-control form-control-sm",
                "accept": ".pdf,.jpg,.jpeg,.png,.webp",
            }
        )

    def clean_employee_certificate(self):
        uploaded = self.cleaned_data["employee_certificate"]
        allowed_ext = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
        extension = ""
        if "." in uploaded.name:
            extension = uploaded.name[uploaded.name.rfind(".") :].lower()
        if extension not in allowed_ext:
            raise forms.ValidationError("Разрешены только PDF или изображения (JPG, PNG, WEBP).")
        max_size = 5 * 1024 * 1024
        if uploaded.size > max_size:
            raise forms.ValidationError("Размер файла не должен превышать 5 МБ.")
        return uploaded
