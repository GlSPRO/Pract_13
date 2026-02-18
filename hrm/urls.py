from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('admin/', include('admin_portal.urls')),
    path('hr/', include('hr_portal.urls')),
    path('', include('core.urls')),
]
