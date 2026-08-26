from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(BaseUserAdmin):
    list_display = ("email", "nombre", "rol", "activo", "is_staff", "fecha_creacion")
    list_filter = ("rol", "activo", "is_staff")
    search_fields = ("email", "nombre")
    ordering = ("nombre",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Información personal", {"fields": ("nombre", "rol", "activo")}),
        ("GLPI", {"fields": ("glpi_user_id",)}),
        ("Permisos Django", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "nombre", "rol", "password1", "password2"),
            },
        ),
    )
