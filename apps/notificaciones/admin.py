from django.contrib import admin

from .models import Notificacion


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ("titulo", "usuario", "tipo", "leida", "creada_en")
    list_filter = ("tipo", "leida", "creada_en")
    search_fields = ("titulo", "mensaje", "usuario__nombre", "usuario__email")
    list_select_related = ("usuario",)
    date_hierarchy = "creada_en"
