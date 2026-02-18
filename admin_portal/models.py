from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ("create", "Создание"),
        ("update", "Изменение"),
        ("lock", "Блокировка"),
        ("unlock", "Разблокировка"),
        ("login", "Вход"),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Пользователь",
        related_name="audit_actions",
    )
    action = models.CharField("Действие", max_length=32, choices=ACTION_CHOICES)
    object_type = models.CharField("Тип объекта", max_length=64)
    object_id = models.CharField("ID объекта", max_length=64)
    details = models.TextField("Детали", blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Запись аудита"
        verbose_name_plural = "Записи аудита"

    def __str__(self) -> str:
        return f"{self.get_action_display()} {self.object_type}:{self.object_id}"
