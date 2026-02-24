from django.contrib import admin

from hr_portal.models import InterviewRequest, InterviewTelegramInvite


admin.site.register(InterviewRequest)
admin.site.register(InterviewTelegramInvite)
