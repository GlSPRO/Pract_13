from django.conf import settings
from django.db import models


class ShiftAssignment(models.Model):
    WORKSHOP_CHOICES = [
        ("Горячий цех", "Горячий цех"),
        ("Холодный цех", "Холодный цех"),
        ("Кондитерский участок", "Кондитерский участок"),
        ("Фасовка", "Фасовка"),
    ]

    date = models.DateField("Дата смены")
    start_time = models.TimeField("Начало")
    end_time = models.TimeField("Окончание")
    workshop = models.CharField("Цех/участок", max_length=64, choices=WORKSHOP_CHOICES)
    planned_staff = models.PositiveSmallIntegerField("План сотрудников")
    assigned_staff = models.PositiveSmallIntegerField("Назначено сотрудников", default=0)
    assigned_employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_shifts",
        verbose_name="Ответственный сотрудник",
    )
    is_acknowledged = models.BooleanField("Сотрудник ознакомлен", default=False)
    acknowledged_at = models.DateTimeField("Ознакомлен в", null=True, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        ordering = ["date", "start_time", "workshop"]
        verbose_name = "Смена"
        verbose_name_plural = "Смены"

    def __str__(self) -> str:
        return f"{self.workshop} {self.date} {self.start_time}-{self.end_time}"


class InterviewRequest(models.Model):
    STATUS_SCHEDULED = "scheduled"
    STATUS_COMPLETED = "completed"
    STATUS_PENDING_APPROVAL = "pending_approval"
    STATUS_REJECTED = "rejected"
    STATUS_HIRED = "hired"

    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "Запланировано"),
        (STATUS_COMPLETED, "Проведено"),
        (STATUS_PENDING_APPROVAL, "На подтверждении у администратора"),
        (STATUS_REJECTED, "Отклонено"),
        (STATUS_HIRED, "Подтверждено"),
    ]

    candidate_name = models.CharField("Имя кандидата", max_length=255)
    phone = models.CharField("Телефон", max_length=32)
    candidate_telegram_chat_id = models.CharField("Telegram chat id кандидата", max_length=32, blank=True)
    interview_at = models.DateTimeField("Дата и время собеседования")
    workshop = models.CharField("Цех/участок", max_length=64)
    notes = models.TextField("Комментарий HR", blank=True)
    status = models.CharField(
        "Статус",
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_SCHEDULED,
    )
    hr_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hr_interviews",
        verbose_name="HR менеджер",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_interviews",
        verbose_name="Подтвердил администратор",
    )
    employee_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interview_origin",
        verbose_name="Созданный сотрудник",
    )
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        ordering = ["-interview_at", "-created_at"]
        verbose_name = "Собеседование"
        verbose_name_plural = "Собеседования"

    def __str__(self) -> str:
        return f"{self.candidate_name} ({self.phone})"


class InterviewTelegramInvite(models.Model):
    interview = models.OneToOneField(
        InterviewRequest,
        on_delete=models.CASCADE,
        related_name="telegram_invite",
        verbose_name="Собеседование",
    )
    token = models.CharField("Токен", max_length=64, unique=True)
    chat_id = models.CharField("Telegram chat id", max_length=32, blank=True)
    linked_at = models.DateTimeField("Связано", null=True, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Telegram-приглашение кандидата"
        verbose_name_plural = "Telegram-приглашения кандидатов"
