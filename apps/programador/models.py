from django.conf import settings
from django.db import models


class Festivo(models.Model):
    """Día festivo calendario (colorea las celdas de azul)."""

    fecha = models.DateField("Fecha", unique=True)
    nombre = models.CharField("Nombre", max_length=100)

    class Meta:
        db_table = "Festivos"
        verbose_name = "Festivo"
        verbose_name_plural = "Festivos"
        ordering = ["fecha"]

    def __str__(self):
        return f"{self.nombre} ({self.fecha})"


class DisponibilidadTecnico(models.Model):
    """Disponibilidad de un técnico en una fecha concreta."""

    class Tipo(models.TextChoices):
        AUSENCIA = "ausencia", "Ausencia"
        NO_AUSENCIA = "no_ausencia", "No ausencia"
        FALTA = "falta", "Falta de disponibilidad"

    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="disponibilidad",
        db_column="TecnicoId",
    )
    fecha = models.DateField("Fecha")
    hora = models.TimeField("Hora", null=True, blank=True)
    tipo = models.CharField(
        "Tipo",
        max_length=20,
        choices=Tipo.choices,
        default=Tipo.AUSENCIA,
    )
    nota = models.CharField("Nota", max_length=200, blank=True, default="")
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disponibilidad_creada",
        db_column="CreadoPorId",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "DisponibilidadTecnicos"
        verbose_name = "Disponibilidad de técnico"
        verbose_name_plural = "Disponibilidad de técnicos"
        constraints = [
            models.UniqueConstraint(fields=["tecnico", "fecha"], name="uq_disponibilidad_tecnico_fecha")
        ]
        ordering = ["fecha"]


class CalendarioEvento(models.Model):
    """Tarea, solicitud, recordatorio, proyecto o anuncio por fecha."""

    class Tipo(models.TextChoices):
        TAREA = "tarea", "Tarea"
        SOLICITUD = "solicitud", "Solicitud"
        RECORDATORIO = "recordatorio", "Recordatorio"
        PROYECTO = "proyecto", "Proyecto"
        ANUNCIO = "anuncio", "Anuncio"

    tipo = models.CharField(max_length=15, choices=Tipo.choices, default=Tipo.TAREA)
    titulo = models.CharField("Titulo", max_length=150)
    descripcion = models.TextField("Descripcion", blank=True, default="")
    fecha = models.DateField("Fecha")
    hora = models.TimeField("Hora", null=True, blank=True)
    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_calendario",
        db_column="TecnicoId",
    )
    ticket = models.ForeignKey(
        "tickets.Ticket",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_calendario",
        db_column="TicketId",
        help_text="Solicitud vinculada cuando tipo = solicitud",
    )
    sitio = models.CharField("Sitio / punto", max_length=80, blank=True, default="")
    grupo = models.CharField("Grupo", max_length=60, blank=True, default="")
    completado = models.BooleanField("Completado", default=False)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_calendario_creados",
        db_column="CreadoPorId",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "CalendarioEventos"
        verbose_name = "Evento de calendario"
        verbose_name_plural = "Eventos de calendario"
        ordering = ["fecha", "hora"]

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.titulo} ({self.fecha})"