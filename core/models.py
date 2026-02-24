from django.conf import settings
from django.db import models


ZONE_CHOICES = [
    ("Горячий цех", "Горячий цех"),
    ("Холодный цех", "Холодный цех"),
    ("Кондитерский участок", "Кондитерский участок"),
    ("Фасовка", "Фасовка"),
]


class JobPosition(models.Model):
    name = models.CharField("Название должности", max_length=150, unique=True)
    is_active = models.BooleanField("Активна", default=True)
    sort_order = models.PositiveSmallIntegerField("Порядок", default=100)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Должность"
        verbose_name_plural = "Справочник должностей"

    def __str__(self) -> str:
        return self.name


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="Пользователь",
    )
    full_name = models.CharField("ФИО", max_length=255)
    position = models.CharField("Должность", max_length=255, blank=True)
    telegram_chat_id = models.CharField("Telegram chat id", max_length=32, blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Профиль"
        verbose_name_plural = "Профили"

    def __str__(self) -> str:
        return self.full_name or self.user.get_username()


class ProfileChangeRequest(models.Model):
    STATUS_NEW = "new"
    STATUS_REVIEW = "review"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_NEW, "Новая"),
        (STATUS_REVIEW, "На рассмотрении"),
        (STATUS_APPROVED, "Подтверждена"),
        (STATUS_REJECTED, "Отклонена"),
    ]

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile_change_requests",
        verbose_name="Сотрудник",
    )
    field_label = models.CharField("Что изменить", max_length=100)
    new_value = models.TextField("Новое значение")
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Заявка на изменение профиля"
        verbose_name_plural = "Заявки на изменение профиля"


class LeaveRequest(models.Model):
    TYPE_SICK = "sick"
    TYPE_VACATION = "vacation"
    TYPE_CHOICES = [
        (TYPE_SICK, "Больничный"),
        (TYPE_VACATION, "Отпуск"),
    ]
    STATUS_SUBMITTED = "submitted"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_SUBMITTED, "Отправлено"),
        (STATUS_APPROVED, "Подтверждено"),
        (STATUS_REJECTED, "Отклонено"),
    ]

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="leave_requests",
        verbose_name="Сотрудник",
    )
    leave_type = models.CharField("Тип", max_length=20, choices=TYPE_CHOICES)
    start_date = models.DateField("Дата начала")
    end_date = models.DateField("Дата окончания")
    note = models.TextField("Комментарий", blank=True)
    document_name = models.CharField("Документ", max_length=255, blank=True)
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default=STATUS_SUBMITTED)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Заявка на больничный/отпуск"
        verbose_name_plural = "Заявки на больничный/отпуск"


class EmployeeTask(models.Model):
    PRIORITY_LOW = 1
    PRIORITY_MEDIUM = 2
    PRIORITY_HIGH = 3
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Низкий"),
        (PRIORITY_MEDIUM, "Средний"),
        (PRIORITY_HIGH, "Высокий"),
    ]

    STATUS_NEW = "new"
    STATUS_PROGRESS = "progress"
    STATUS_DONE = "done"
    STATUS_CHOICES = [
        (STATUS_NEW, "Новая"),
        (STATUS_PROGRESS, "В работе"),
        (STATUS_DONE, "Выполнена"),
    ]

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_tasks",
        verbose_name="Сотрудник",
    )
    title = models.CharField("Задача", max_length=255)
    description = models.TextField("Описание", blank=True)
    priority = models.PositiveSmallIntegerField("Приоритет", choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    due_date = models.DateField("Срок", null=True, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        ordering = ["-priority", "status", "due_date", "-created_at"]
        verbose_name = "Задача сотрудника"
        verbose_name_plural = "Задачи сотрудников"


class EmployeeZoneAccess(models.Model):
    LEVEL_BASIC = "basic"
    LEVEL_MIDDLE = "middle"
    LEVEL_HIGH = "high"
    LEVEL_CHOICES = [
        (LEVEL_BASIC, "Базовая"),
        (LEVEL_MIDDLE, "Средняя"),
        (LEVEL_HIGH, "Высокая"),
    ]

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="zone_accesses",
        verbose_name="Сотрудник",
    )
    zone = models.CharField("Зона/участок", max_length=64, choices=ZONE_CHOICES)
    qualification_level = models.CharField("Уровень квалификации", max_length=20, choices=LEVEL_CHOICES)
    is_active = models.BooleanField("Активно", default=True)
    granted_at = models.DateTimeField("Выдано", auto_now_add=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_zone_accesses",
        verbose_name="Кто выдал",
    )

    class Meta:
        unique_together = ("employee", "zone")
        verbose_name = "Допуск к зоне"
        verbose_name_plural = "Допуски к зонам"


class UpskillDirective(models.Model):
    STATUS_ASSIGNED = "assigned"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_EMPLOYEE_CONFIRMED = "employee_confirmed"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_ASSIGNED, "Назначено HR"),
        (STATUS_IN_PROGRESS, "В обучении"),
        (STATUS_EMPLOYEE_CONFIRMED, "Сотрудник подтвердил прохождение"),
        (STATUS_APPROVED, "Подтверждено HR"),
        (STATUS_REJECTED, "Отклонено HR"),
    ]

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="upskill_directives",
        verbose_name="Сотрудник",
    )
    target_zone = models.CharField("Целевая зона", max_length=64, choices=ZONE_CHOICES)
    target_level = models.CharField(
        "Целевой уровень",
        max_length=20,
        choices=EmployeeZoneAccess.LEVEL_CHOICES,
        default=EmployeeZoneAccess.LEVEL_BASIC,
    )
    rationale = models.TextField("Обоснование необходимости")
    status = models.CharField("Статус", max_length=30, choices=STATUS_CHOICES, default=STATUS_ASSIGNED)
    planned_date = models.DateField("Плановая дата", null=True, blank=True)
    employee_comment = models.TextField("Комментарий сотрудника", blank=True)
    employee_certificate = models.FileField(
        "Сертификат сотрудника",
        upload_to="qualification_certificates/",
        blank=True,
        null=True,
    )
    employee_certificate_uploaded_at = models.DateTimeField("Сертификат загружен", null=True, blank=True)
    hr_comment = models.TextField("Комментарий HR", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_upskill_directives",
        verbose_name="Назначил HR",
    )
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Назначение на повышение квалификации"
        verbose_name_plural = "Назначения на повышение квалификации"
