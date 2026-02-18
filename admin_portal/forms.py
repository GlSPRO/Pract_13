import secrets
from typing import Optional

from django import forms
from django.contrib.auth.models import Group, User

from core.models import Profile


GROUP_CHOICES = (
    ("admin", "Администратор"),
    ("hr", "HR"),
    ("staff", "Сотрудник"),
)


def ensure_group(code: str) -> Optional[Group]:
    mapping = {"admin": "Администратор", "hr": "HR", "staff": "Сотрудник"}
    name = mapping.get(code)
    if not name:
        return None
    group, _ = Group.objects.get_or_create(name=name)
    return group


class UserCreateForm(forms.Form):
    username = forms.CharField(label="Логин", max_length=150)
    full_name = forms.CharField(label="ФИО", max_length=255)
    group = forms.ChoiceField(label="Группа", choices=GROUP_CHOICES)
    password = forms.CharField(label="Пароль", required=False, disabled=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        generated = secrets.token_urlsafe(8)
        self.generated_password = generated
        self.fields["password"].initial = generated

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Пользователь с таким логином уже существует.")
        return username

    def save(self, actor: User):
        username = self.cleaned_data["username"]
        full_name = self.cleaned_data["full_name"]
        group_code = self.cleaned_data["group"]
        group = ensure_group(group_code)

        user = User.objects.create(username=username, is_active=True)
        user.set_password(self.generated_password)
        user.save()

        Profile.objects.update_or_create(user=user, defaults={"full_name": full_name})
        if group:
            user.groups.set([group])
        user.save()
        return user, self.generated_password


class UserUpdateForm(forms.Form):
    full_name = forms.CharField(label="ФИО", max_length=255)
    group = forms.ChoiceField(label="Группа", choices=GROUP_CHOICES)
    status = forms.ChoiceField(
        label="Статус",
        choices=(("active", "Активен"), ("locked", "Заблокирован")),
    )

    def __init__(self, *args, **kwargs):
        self.user_instance: User = kwargs.pop("user_instance")
        super().__init__(*args, **kwargs)
        profile = getattr(self.user_instance, "profile", None)
        self.fields["full_name"].initial = profile.full_name if profile else ""
        current_group = self.user_instance.groups.first()
        back_map = {"Администратор": "admin", "HR": "hr", "Сотрудник": "staff"}
        self.fields["group"].initial = back_map.get(current_group.name) if current_group else ""
        self.fields["status"].initial = "active" if self.user_instance.is_active else "locked"

    def save(self, actor: User):
        full_name = self.cleaned_data["full_name"]
        group_code = self.cleaned_data["group"]
        status = self.cleaned_data["status"]

        Profile.objects.update_or_create(
            user=self.user_instance,
            defaults={"full_name": full_name},
        )

        group = ensure_group(group_code)
        if group:
            self.user_instance.groups.set([group])

        self.user_instance.is_active = status == "active"
        self.user_instance.save()
        return self.user_instance
