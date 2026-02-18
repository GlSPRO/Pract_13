from django.conf import settings
from django.db import models


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
