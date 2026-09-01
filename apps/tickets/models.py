import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import models
from django.db.models import Count, Q
from django.utils import timezone

from .sla import horas_por_prioridad, formatear_duracion


class Categoria(models.Model):
    """
    Categorias alineadas a la infraestructura Dogger (STATU QUO):
    SIESA ERP/Web, POS, red/firewall, servidores, correo, endpoints, etc.
    """
    grupo = models.CharField("Grupo", max_length=50)
    nombre = models.CharField("Nombre", max_length=80)
    activo = models.BooleanField(default=True)
    prioridad_default = models.CharField(
        "Prioridad por defecto (ANS)",
        max_length=20,
        choices=[("baja", "Baja"), ("media", "Media"), ("alta", "Alta"), ("urgente", "Urgente")],
        default="media",
        help_text="Prioridad que se asigna automáticamente según el ANS de esta categoría",
    )
    ans_horas = models.PositiveIntegerField(
        "Horas ANS",
        default=24,
        help_text="Tiempo máximo (horas) para resolver tickets de esta categoría. Si no se define, se usa el valor base de la prioridad.",
    )
    glpi_category_id = models.PositiveIntegerField(
        "ID categoria GLPI", null=True, blank=True
    )
    tecnico_default = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="categorias_asignadas",
        db_column="TecnicoDefaultId",
        verbose_name="Técnico por defecto",
        help_text="Se asigna automáticamente a los tickets nuevos de esta categoría",
    )

    class Meta:
        db_table = "Categorias"
        verbose_name = "Categoria"
        verbose_name_plural = "Categorias"
        unique_together = [("grupo", "nombre")]
        ordering = ["grupo", "nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.grupo})"

    @classmethod
    def arbol(cls):
        """
        Agrupa las categorías por 'grupo' (categoría principal encapsulando
        subcategorías relacionadas), con conteo de tickets por cada una.
        """
        from django.db.models import Count as _Count

        cats = (
            cls.objects.filter(activo=True)
            .annotate(tickets_count=_Count("tickets"))
            .order_by("grupo", "nombre")
        )
        arbol = {}
        for c in cats:
            arbol.setdefault(c.grupo, []).append(c)
        return [
            {"grupo": grupo, "subcategorias": subs, "total": sum(s.tickets_count for s in subs)}
            for grupo, subs in arbol.items()
        ]


class Ticket(models.Model):
    class Prioridad(models.TextChoices):
        BAJA = "baja", "Baja"
        MEDIA = "media", "Media"
        ALTA = "alta", "Alta"
        URGENTE = "urgente", "Urgente"

    class Estado(models.TextChoices):
        ABIERTO = "abierto", "Abierto"
        EN_PROGRESO = "en-progreso", "En progreso"
        RESUELTO = "resuelto", "Resuelto"
        CERRADO = "cerrado", "Cerrado"

    codigo = models.CharField("Codigo", max_length=12, unique=True, editable=False)
    titulo = models.CharField("Titulo", max_length=150)
    descripcion = models.TextField("Descripcion")
    prioridad = models.CharField(
        max_length=10,
        choices=Prioridad.choices,
        default=Prioridad.MEDIA,
    )
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets",
        db_column="CategoriaId",
    )
    estado = models.CharField(
        max_length=15,
        choices=Estado.choices,
        default=Estado.ABIERTO,
    )
    solicitante_nombre = models.CharField("Solicitante", max_length=100)
    solicitante_email = models.EmailField("Correo", max_length=150, blank=True, null=True)
    solicitante_punto = models.CharField(
        "Punto / sede / equipo",
        max_length=80,
        blank=True,
        null=True,
        help_text="Ej: Caja 3 Envigado, PC-P1 PC5, Server Principal",
    )
    tecnico_asignado = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets_asignados",
        db_column="TecnicoAsignadoId",
    )
    asignacion_automatica = models.BooleanField(
        "Asignación automática",
        default=False,
        help_text="True cuando el técnico se asignó por regla de categoría",
    )
    glpi_id = models.PositiveIntegerField("ID GLPI", null=True, blank=True, db_index=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "Tickets"
        verbose_name = "Ticket"
        verbose_name_plural = "Tickets"
        ordering = ["-fecha_creacion"]
        indexes = [
            models.Index(fields=["estado"], name="IX_Tickets_Estado"),
            models.Index(fields=["prioridad"], name="IX_Tickets_Prioridad"),
            models.Index(fields=["fecha_creacion"], name="IX_Tickets_Fecha"),
        ]

    def __str__(self):
        return f"{self.codigo} — {self.titulo}"

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = self._generar_codigo()
        if self.estado in (self.Estado.RESUELTO, self.Estado.CERRADO) and not self.fecha_cierre:
            self.fecha_cierre = timezone.now()
        if self.estado in (self.Estado.ABIERTO, self.Estado.EN_PROGRESO):
            self.fecha_cierre = None
        super().save(*args, **kwargs)

    @staticmethod
    def _generar_codigo():
        total = Ticket.objects.count() + 1
        return f"HD-{total:04d}"

    @property
    def adjuntos_pendientes_glpi(self) -> bool:
        """True si hay adjuntos que aún no se han subido a GLPI."""
        if not self.pk:
            return False
        return self.adjuntos.filter(sincronizado_glpi=False).exists()

    # ------------------------------------------------------------------
    # ANS: tiempos objetivo de resolución según prioridad de la categoría
    # ------------------------------------------------------------------
    @property
    def ans_horas(self) -> int:
        if self.categoria_id and self.categoria and self.categoria.ans_horas:
            return self.categoria.ans_horas
        return horas_por_prioridad(self.prioridad)

    @property
    def fecha_limite_ans(self):
        if not self.fecha_creacion:
            return None
        return self.fecha_creacion + timedelta(hours=self.ans_horas)

    @property
    def info_ans(self):
        """
        Tupla (estado, texto, detalle) para mostrar el ANS del ticket.

        estado: 'ok' | 'por-vencer' | 'vencido' | 'resuelto' | None
          - abiertos/en progreso: tiempo restante para el límite (o vencido).
          - resuelto/cerrado: tiempo tomado en resolverse.
        """
        if self.estado in (self.Estado.RESUELTO, self.Estado.CERRADO):
            if self.fecha_cierre and self.fecha_creacion:
                duracion = self.fecha_cierre - self.fecha_creacion
                return ("resuelto", f"Resuelto en {formatear_duracion(duracion)}", None)
            return ("resuelto", "Resuelto", None)
        if not self.fecha_creacion or not self.ans_horas:
            return (None, "Sin ANS", None)
        ahora = timezone.now()
        limite = self.fecha_limite_ans
        detalle = f"Límite {limite:%d/%m %H:%M} · ANS {self.ans_horas}h · {self.get_prioridad_display()}"
        if ahora >= limite:
            return (
                "vencido",
                f"ANS vencido {formatear_duracion(ahora - limite)}",
                detalle,
            )
        restante = limite - ahora
        total = limite - self.fecha_creacion
        margen = total * 0.25
        estado = "por-vencer" if (restante <= margen or restante <= timedelta(hours=2)) else "ok"
        return (estado, f"Faltan {formatear_duracion(restante)}", detalle)

    @classmethod
    def estadisticas(cls):
        return cls.objects.aggregate(
            total=Count("id"),
            abiertos=Count("id", filter=Q(estado=cls.Estado.ABIERTO)),
            en_progreso=Count("id", filter=Q(estado=cls.Estado.EN_PROGRESO)),
            resueltos=Count("id", filter=Q(estado=cls.Estado.RESUELTO)),
            cerrados=Count("id", filter=Q(estado=cls.Estado.CERRADO)),
        )

    @classmethod
    def tiempo_promedio_resolucion_horas(cls, queryset=None):
        """
        KPI: promedio de horas entre creación y cierre, para tickets
        resueltos o cerrados que ya tienen fecha_cierre.
        Retorna string legible o None.
        """
        qs = queryset if queryset is not None else cls.objects.all()
        cerrados = qs.filter(
            fecha_cierre__isnull=False,
        ).values_list("fecha_creacion", "fecha_cierre")
        if not cerrados:
            return None
        total_horas = 0.0
        n = 0
        for creacion, cierre in cerrados:
            delta = cierre - creacion
            total_horas += delta.total_seconds() / 3600
            n += 1
        if not n:
            return None
        promedio = total_horas / n
        if promedio < 1:
            return f"{int(promedio * 60)}min"
        elif promedio < 24:
            return f"{promedio:.1f}h"
        else:
            dias = promedio / 24
            return f"{dias:.1f}d"


def adjunto_upload_to(instance, filename):
    ext = Path(filename).suffix.lower() or ".bin"
    codigo = instance.ticket.codigo if instance.ticket_id else "tmp"
    return f"adjuntos/{codigo}/{uuid.uuid4().hex}{ext}"


class TicketAdjunto(models.Model):
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="adjuntos",
        db_column="TicketId",
    )
    nombre_original = models.CharField(max_length=255)
    archivo = models.FileField(upload_to=adjunto_upload_to, max_length=500)
    mime_type = models.CharField(max_length=100)
    tamano_bytes = models.PositiveIntegerField()
    subido_por = models.CharField(max_length=100, blank=True, null=True)
    fecha_subida = models.DateTimeField(auto_now_add=True)
    sincronizado_glpi = models.BooleanField(
        default=False,
        help_text="True cuando el archivo ya fue subido a GLPI como documento del ticket",
    )

    class Meta:
        db_table = "TicketAdjuntos"
        verbose_name = "Adjunto"
        verbose_name_plural = "Adjuntos"
        ordering = ["fecha_subida"]

    def __str__(self):
        return self.nombre_original

    @property
    def es_imagen(self):
        return (self.mime_type or "").startswith("image/")


class TicketComentario(models.Model):
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="comentarios",
        db_column="TicketId",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comentarios",
        db_column="UsuarioId",
    )
    autor_nombre = models.CharField(max_length=100, blank=True, default="")
    comentario = models.TextField()
    es_interno = models.BooleanField(
        default=False,
        help_text="Si es True, solo lo ve el staff",
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "TicketComentarios"
        verbose_name = "Comentario"
        verbose_name_plural = "Comentarios"
        ordering = ["fecha"]

    def __str__(self):
        return f"Comentario en {self.ticket.codigo}"


class GlpiEvento(models.Model):
    """
    Bitácora de eventos recibidos desde el webhook de GLPI.
    Alimenta el panel de 'Actividad reciente' del dashboard.
    """
    class Tipo(models.TextChoices):
        CAMBIO_ESTADO = "cambio-estado", "Cambio de estado"
        SEGUIMIENTO = "seguimiento", "Nuevo seguimiento"
        OTRO = "otro", "Otro"

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="eventos_glpi",
        null=True,
        blank=True,
        db_column="TicketId",
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.OTRO)
    descripcion = models.CharField(max_length=255)
    payload_bruto = models.JSONField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "GlpiEventos"
        verbose_name = "Evento GLPI"
        verbose_name_plural = "Eventos GLPI"
        ordering = ["-fecha"]
        indexes = [
            models.Index(fields=["-fecha"], name="IX_GlpiEventos_Fecha"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.descripcion}"
