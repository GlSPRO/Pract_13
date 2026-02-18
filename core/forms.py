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
