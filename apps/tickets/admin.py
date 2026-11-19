from django.contrib import admin
from django import forms
from .models import (
    Categoria,
    CategoriaGrupo,
    ElementoMiLista,
    MensajeCorporativo,
    MonitoreoAuditoria,
    Ticket,
    TicketAdjunto,
    TicketComentario,
    ZonaObservador,
    ConfiguracionAutoasignacion,
    PerfilAutoasignacion,
    DecisionAutoasignacion,
)


class ConfiguracionAutoasignacionForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionAutoasignacion
        fields = "__all__"

    def clean(self):
        datos = super().clean()
        for campo in ("peso_urgente", "peso_alta", "peso_media", "peso_baja"):
            if datos.get(campo) is not None and datos[campo] <= 0:
                self.add_error(campo, "El peso debe ser mayor que cero.")
        if datos.get("margen_puntos") is not None and datos["margen_puntos"] > 100:
            self.add_error("margen_puntos", "El margen no puede superar 100 puntos porcentuales.")
        return datos


class EscriturasCoordinadasAdmin:
    """Mantiene el bloqueo también durante guardado de relaciones M2M."""
    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if request.method == "POST":
            from apps.tickets.services.autoasignacion_transaccional import coordinacion_asignacion
            with coordinacion_asignacion():
                return super().changeform_view(request, object_id, form_url, extra_context)
        return super().changeform_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        if request.method == "POST":
            from apps.tickets.services.autoasignacion_transaccional import coordinacion_asignacion
            with coordinacion_asignacion():
                return super().changelist_view(request, extra_context)
        return super().changelist_view(request, extra_context)


class SoloSuperusuarioAdmin(EscriturasCoordinadasAdmin, admin.ModelAdmin):
    def has_module_permission(self, request):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ConfiguracionAutoasignacion)
class ConfiguracionAutoasignacionAdmin(SoloSuperusuarioAdmin):
    form = ConfiguracionAutoasignacionForm
    list_display = ("id", "activa", "margen_puntos", "secuencia")
    readonly_fields = ("activa", "secuencia")

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not ConfiguracionAutoasignacion.objects.exists()


@admin.register(PerfilAutoasignacion)
class PerfilAutoasignacionAdmin(SoloSuperusuarioAdmin):
    list_display = ("tecnico", "habilitado", "cobertura_general", "capacidad", "carga_actual", "ocupacion_actual", "orden_rotacion")
    list_filter = ("habilitado",)
    search_fields = ("tecnico__email", "tecnico__nombre")
    filter_horizontal = ("categorias", "puntos_cobertura")
    readonly_fields = ("orden_rotacion",)

    @admin.display(description="Carga ponderada")
    def carga_actual(self, perfil):
        config = ConfiguracionAutoasignacion.objects.filter(pk=1).first()
        if not config:
            return "Sin configuración"
        pesos = {"urgente": config.peso_urgente, "alta": config.peso_alta,
                 "media": config.peso_media, "baja": config.peso_baja}
        from django.db.models import Count
        filas = Ticket.objects.filter(tecnico_asignado=perfil.tecnico, estado__in=("abierto", "en-progreso")).values("prioridad").annotate(total=Count("pk"))
        if any(fila["prioridad"] not in pesos for fila in filas):
            return "Prioridad desconocida"
        return sum(fila["total"] * pesos[fila["prioridad"]] for fila in filas)

    @admin.display(description="Ocupación")
    def ocupacion_actual(self, perfil):
        carga = self.carga_actual(perfil)
        return f"{carga / perfil.capacidad * 100:.1f}%" if isinstance(carga, int) and perfil.capacidad else "No disponible"


@admin.register(DecisionAutoasignacion)
class DecisionAutoasignacionAdmin(SoloSuperusuarioAdmin):
    list_display = ("fecha", "ticket", "tecnico", "prioridad", "motivo", "carga", "capacidad")
    list_filter = ("motivo", "prioridad")
    readonly_fields = ("fecha", "ticket", "tecnico", "prioridad", "categoria_nombre", "motivo", "carga", "capacidad")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Categoria)
class CategoriaAdmin(EscriturasCoordinadasAdmin, admin.ModelAdmin):
    list_display = ("nombre", "grupo", "activo", "glpi_category_id", "tecnico_default")
    list_filter = ("grupo", "activo")
    search_fields = ("nombre", "grupo")
    list_editable = ("tecnico_default",)


@admin.register(CategoriaGrupo)
class CategoriaGrupoAdmin(admin.ModelAdmin):
    search_fields = ("nombre",)


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
        "codigo", "titulo", "prioridad", "estado", "modo", "solicitante_nombre",
        "categoria", "tecnico_asignado", "glpi_id", "fecha_creacion",
    )
    list_filter = ("estado", "prioridad", "modo", "categoria")
    search_fields = ("codigo", "titulo", "solicitante_nombre")
    readonly_fields = ("codigo", "fecha_creacion", "fecha_actualizacion", "glpi_id")
    inlines = [AdjuntoInline, ComentarioInline]
    date_hierarchy = "fecha_creacion"

    def save_model(self, request, obj, form, change):
        from apps.tickets.services.autoasignacion_transaccional import coordinacion_asignacion

        with coordinacion_asignacion(using=obj._state.db or "default"):
            if change:
                actual = Ticket.objects.select_for_update().get(pk=obj.pk)
                if "tecnico_asignado" not in form.changed_data:
                    obj.tecnico_asignado_id = actual.tecnico_asignado_id
                    obj.asignacion_automatica = actual.asignacion_automatica
                    obj.asignacion_manual_protegida = actual.asignacion_manual_protegida
                else:
                    obj.asignacion_automatica = False
                    obj.asignacion_manual_protegida = True
            elif obj.tecnico_asignado_id:
                obj.asignacion_automatica = False
                obj.asignacion_manual_protegida = True
            super().save_model(request, obj, form, change)


@admin.register(TicketAdjunto)
class TicketAdjuntoAdmin(admin.ModelAdmin):
    list_display = ("nombre_original", "ticket", "mime_type", "tamano_bytes", "fecha_subida")


@admin.register(ZonaObservador)
class ZonaObservadorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "observador", "creado_en")
    list_filter = ("observador",)
    search_fields = ("nombre", "observador__email", "observador__nombre")
    readonly_fields = ("creado_en",)


@admin.register(ElementoMiLista)
class ElementoMiListaAdmin(admin.ModelAdmin):
    list_display = ("observador", "tipo", "usuario_email", "punto", "zona", "creado_en")
    list_filter = ("tipo", "zona")
    search_fields = ("usuario_email", "observador__email")
    readonly_fields = ("creado_en",)


@admin.register(MensajeCorporativo)
class MensajeCorporativoAdmin(admin.ModelAdmin):
    list_display = ("autor_nombre", "usuario", "fecha")
    list_filter = ("fecha",)
    search_fields = ("texto", "autor_nombre", "usuario__email")
    readonly_fields = ("fecha",)


@admin.register(MonitoreoAuditoria)
class MonitoreoAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "accion", "zona_nombre", "cuenta", "actor", "observador", "resultado")
    list_filter = ("accion", "resultado")
    search_fields = ("zona_nombre", "detalle", "cuenta", "motivo", "actor__email", "observador__email")
    readonly_fields = ("fecha", "ip_origen", "version_sistema")
