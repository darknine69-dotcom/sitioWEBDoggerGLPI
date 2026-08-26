from django.contrib import admin
from .models import Categoria, Ticket, TicketAdjunto, TicketComentario


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "grupo", "activo", "glpi_category_id", "tecnico_default")
    list_filter = ("grupo", "activo")
    search_fields = ("nombre", "grupo")
    list_editable = ("tecnico_default",)


class AdjuntoInline(admin.TabularInline):
    model = TicketAdjunto
    extra = 0
    readonly_fields = ("nombre_original", "mime_type", "tamano_bytes", "fecha_subida")


class ComentarioInline(admin.TabularInline):
    model = TicketComentario
    extra = 0
    readonly_fields = ("fecha",)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = (
        "codigo", "titulo", "prioridad", "estado", "solicitante_nombre",
        "categoria", "tecnico_asignado", "glpi_id", "fecha_creacion",
    )
    list_filter = ("estado", "prioridad", "categoria")
    search_fields = ("codigo", "titulo", "solicitante_nombre")
    readonly_fields = ("codigo", "fecha_creacion", "fecha_actualizacion", "glpi_id")
    inlines = [AdjuntoInline, ComentarioInline]
    date_hierarchy = "fecha_creacion"


@admin.register(TicketAdjunto)
class TicketAdjuntoAdmin(admin.ModelAdmin):
    list_display = ("nombre_original", "ticket", "mime_type", "tamano_bytes", "fecha_subida")
