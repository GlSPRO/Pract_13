from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.utils import timezone

from admin_portal.models import AuditLog
from core.models import EmployeeTask, LeaveRequest, Profile, ProfileChangeRequest
from hr_portal.models import InterviewRequest
from hr_portal.models import ShiftAssignment


class Command(BaseCommand):
    help = "Создает тестовые данные для админ-портала и графиков дашборда."

    def handle(self, *args, **options):
        groups = {}
        for name in ["Администратор", "HR", "Сотрудник"]:
            group, _ = Group.objects.get_or_create(name=name)
            groups[name] = group

        users_data = [
            ("admin", "admin12345", "Системный Администратор", "Администратор"),
            ("hr", "hr12345", "Елена Кадрова", "HR"),
            ("emp", "emp12345", "Иван Сотрудников", "Сотрудник"),
            ("hotchef", "demo12345", "Алексей Горячев", "Сотрудник"),
            ("coldchef", "demo12345", "Мария Холодова", "Сотрудник"),
            ("packer", "demo12345", "Олег Фасовкин", "Сотрудник"),
        ]

        created_users = {}
        for username, password, full_name, group_name in users_data:
            user, created = User.objects.get_or_create(username=username)
            user.set_password(password)
            user.is_active = True
            user.save()
            user.groups.set([groups[group_name]])
            Profile.objects.update_or_create(
                user=user,
                defaults={"full_name": full_name, "position": "Тестовая должность"},
            )
            created_users[username] = user

        # Тестовый график смен для HR-портала
        ShiftAssignment.objects.all().delete()
        today = timezone.localdate()
        shifts = [
            (0, "08:00", "17:00", "Горячий цех", 14, 12, "hotchef"),
            (0, "09:00", "18:00", "Холодный цех", 10, 11, "coldchef"),
            (0, "10:00", "19:00", "Кондитерский участок", 8, 7, "emp"),
            (1, "08:00", "17:00", "Фасовка", 9, 9, "packer"),
            (1, "09:00", "18:00", "Горячий цех", 14, 13, "hotchef"),
            (1, "10:00", "19:00", "Холодный цех", 10, 9, "coldchef"),
            (2, "08:00", "17:00", "Кондитерский участок", 8, 8, "emp"),
            (2, "09:00", "18:00", "Фасовка", 9, 8, "packer"),
        ]
        for shift_day, start_time, end_time, workshop, planned, assigned, username in shifts:
            ShiftAssignment.objects.create(
                date=today + timedelta(days=shift_day),
                start_time=start_time,
                end_time=end_time,
                workshop=workshop,
                planned_staff=planned,
                assigned_staff=assigned,
                assigned_employee=created_users.get(username),
                is_acknowledged=False,
            )

        emp_user = created_users["emp"]
        ProfileChangeRequest.objects.filter(employee=emp_user).delete()
        LeaveRequest.objects.filter(employee=emp_user).delete()
        EmployeeTask.objects.filter(employee=emp_user).delete()

        ProfileChangeRequest.objects.create(
            employee=emp_user,
            field_label="Контактный номер",
            new_value="+7 900 123 45 67",
            status=ProfileChangeRequest.STATUS_REVIEW,
        )
        LeaveRequest.objects.create(
            employee=emp_user,
            leave_type=LeaveRequest.TYPE_VACATION,
            start_date=today + timedelta(days=14),
            end_date=today + timedelta(days=20),
            status=LeaveRequest.STATUS_SUBMITTED,
            note="Плановый отпуск",
            document_name="vacation_request.pdf",
        )
        LeaveRequest.objects.create(
            employee=emp_user,
            leave_type=LeaveRequest.TYPE_SICK,
            start_date=today - timedelta(days=10),
            end_date=today - timedelta(days=6),
            status=LeaveRequest.STATUS_APPROVED,
            note="Больничный закрыт",
            document_name="sick_leave.pdf",
        )
        EmployeeTask.objects.create(
            employee=emp_user,
            title="Ознакомиться с графиком смен",
            description="Проверить все смены на текущую неделю и подтвердить.",
            priority=EmployeeTask.PRIORITY_HIGH,
            status=EmployeeTask.STATUS_PROGRESS,
            due_date=today + timedelta(days=1),
        )
        EmployeeTask.objects.create(
            employee=emp_user,
            title="Подтвердить технику безопасности",
            description="Пройти инструктаж и отметить задачу выполненной.",
            priority=EmployeeTask.PRIORITY_MEDIUM,
            status=EmployeeTask.STATUS_NEW,
            due_date=today + timedelta(days=3),
        )

        # Тестовые собеседования для HR -> Администратор
        InterviewRequest.objects.all().delete()
        interviews = [
            ("Павел Новиков", "+7 900 101-20-30", 1, "Горячий цех", InterviewRequest.STATUS_SCHEDULED, "Первичное интервью", ""),
            ("Ирина Кузьмина", "+7 900 222-33-44", 0, "Холодный цех", InterviewRequest.STATUS_COMPLETED, "Собеседование успешно", ""),
            ("Олег Сидоров", "+7 900 777-88-99", -1, "Фасовка", InterviewRequest.STATUS_PENDING_APPROVAL, "Рекомендуется к найму", ""),
            ("Мария Белова", "+7 900 555-11-22", -2, "Кондитерский участок", InterviewRequest.STATUS_REJECTED, "Не подходит по графику", ""),
        ]
        for name, phone, day_offset, workshop, status, notes, chat_id in interviews:
            InterviewRequest.objects.create(
                candidate_name=name,
                phone=phone,
                candidate_telegram_chat_id=chat_id,
                interview_at=timezone.now() + timedelta(days=day_offset),
                workshop=workshop,
                notes=notes,
                status=status,
                hr_manager=created_users["hr"],
            )

        # Данные для графика замен/переназначений (считываются из AuditLog)
        AuditLog.objects.filter(
            action="update",
            details__icontains="переназначение смены",
        ).delete()

        now = timezone.now()
        replacement_events = [
            (1, "Переназначение смены: Горячий цех 08:00"),
            (2, "Переназначение смены: Холодный цех 10:00"),
            (3, "Переназначение смены: Фасовка 12:00"),
            (5, "Переназначение смены: Горячий цех 14:00"),
            (7, "Переназначение смены: Кондитерский участок 16:00"),
            (9, "Переназначение смены: Холодный цех 08:00"),
            (12, "Переназначение смены: Фасовка 18:00"),
            (15, "Переназначение смены: Горячий цех 10:00"),
            (18, "Переназначение смены: Кондитерский участок 12:00"),
            (21, "Переназначение смены: Холодный цех 14:00"),
            (24, "Переназначение смены: Горячий цех 18:00"),
            (27, "Переназначение смены: Фасовка 20:00"),
        ]

        actor = created_users["admin"]
        for days_ago, details in replacement_events:
            log = AuditLog.objects.create(
                actor=actor,
                action="update",
                object_type="shift_assignment",
                object_id=str(days_ago),
                details=details,
            )
            AuditLog.objects.filter(pk=log.pk).update(created_at=now - timedelta(days=days_ago))

        # Базовые записи аудита для списка
        AuditLog.objects.get_or_create(
            actor=created_users["admin"],
            action="create",
            object_type="user",
            object_id=str(created_users["hr"].pk),
            defaults={"details": "Создан пользователь hr"},
        )
        AuditLog.objects.get_or_create(
            actor=created_users["admin"],
            action="lock",
            object_type="user",
            object_id=str(created_users["emp"].pk),
            defaults={"details": "Демонстрационная блокировка"},
        )
        AuditLog.objects.get_or_create(
            actor=created_users["admin"],
            action="unlock",
            object_type="user",
            object_id=str(created_users["emp"].pk),
            defaults={"details": "Демонстрационная разблокировка"},
        )

        self.stdout.write(self.style.SUCCESS("Тестовые данные созданы/обновлены."))
        self.stdout.write("Логины: admin/admin12345, hr/hr12345, emp/emp12345")
