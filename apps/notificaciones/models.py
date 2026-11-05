from django.conf import settings
from django.db import models
from django.utils import timezone


class ClaveNotificacion(models.Model):
    """Reserva atómica de claves no vacías por destinatario."""
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    clave = models.CharField(max_length=140)
    notificacion = models.OneToOneField("Notificacion", on_delete=models.CASCADE, related_name="reserva_clave")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["usuario", "clave"], name="uq_notif_usuario_clave")]


class AlertaOperativa(models.Model):
    class Estado(models.TextChoices):
        ABIERTA = "abierta", "Abierta"
        RECONOCIDA = "reconocida", "Reconocida"
        RESUELTA = "resuelta", "Resuelta"

    ticket = models.ForeignKey("tickets.Ticket", null=True, blank=True, on_delete=models.SET_NULL, related_name="alertas_operativas")
    clave_origen = models.CharField(max_length=160, unique=True)
    codigo_ticket = models.CharField(max_length=40, blank=True, default="")
    titulo_ticket = models.CharField(max_length=200, blank=True, default="")
    tipo = models.CharField(max_length=30, default="ans_vencido")
    severidad = models.CharField(max_length=16, default="alta")
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.ABIERTA)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="alertas_operativas")
    creada_en = models.DateTimeField(auto_now_add=True)
    reconocida_en = models.DateTimeField(null=True, blank=True)
    resuelta_en = models.DateTimeField(null=True, blank=True)
    ultima_actividad_en = models.DateTimeField(null=True, blank=True)
    inactividad_segundos = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["estado", "-creada_en"], name="alerta_estado_fecha_idx")]


class HistorialAlerta(models.Model):
    alerta = models.ForeignKey(AlertaOperativa, on_delete=models.CASCADE, related_name="historial")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    accion = models.CharField(max_length=24)
    detalle = models.CharField(max_length=500, blank=True, default="")
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada_en", "-pk"]


class EntregaEscalamiento(models.Model):
    alerta = models.ForeignKey(AlertaOperativa, on_delete=models.CASCADE, related_name="escalamientos")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["alerta", "usuario"], name="uq_escalamiento_alerta_usuario")]


class Notificacion(models.Model):
    """Aviso que vive en la campana del encabezado de Dogger.

    Cada notificación tiene un icono del sprite, un texto y una URL: al
    pulsarla lleva al ticket, evento o vista relacionada, y con la "x" se
    quita de la lista. `clave` evita repetir el mismo aviso (por ejemplo, el
    recordatorio diario de tickets pendientes).
    """

    class Tipo(models.TextChoices):
        BIENVENIDA = "bienvenida", "Bienvenida"
        TICKET_NUEVO = "ticket_nuevo", "Ticket nuevo"
        TICKET_CERRADO = "ticket_cerrado", "Ticket cerrado"
        TICKET_EDITADO = "ticket_editado", "Ticket editado"
        TICKET_RECORDATORIO = "ticket_recordatorio", "Recordatorio de tickets"
        EVENTO = "evento", "Tarea o evento"
        SISTEMA = "sistema", "Sistema"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notificaciones",
        db_column="UsuarioId",
    )
    tipo = models.CharField(max_length=20, choices=Tipo, default=Tipo.SISTEMA, db_column="Tipo")
    titulo = models.CharField(max_length=140, db_column="Titulo")
    mensaje = models.CharField(max_length=300, db_column="Mensaje")
    icono = models.CharField(max_length=30, default="i-bell", db_column="Icono")
    url = models.CharField(max_length=255, blank=True, default="", db_column="Url")
    clave = models.CharField(max_length=140, blank=True, default="", db_column="Clave")
    actor = models.CharField(
        "Responsable", max_length=100, blank=True, default="",
        db_column="Actor",
        help_text="Quién generó el evento (vacío = sistema).",
    )
    actor_rol = models.CharField(
        "Rol del responsable", max_length=20, blank=True, default="",
        db_column="ActorRol",
        help_text="De dónde viene el aviso: técnico, usuario, etc.",
    )
    leida = models.BooleanField(default=False, db_column="Leida")
    mostrada_en = models.DateTimeField(null=True, blank=True, db_column="MostradaEn")
    leida_en = models.DateTimeField(null=True, blank=True, db_column="LeidaEn")
    archivada_en = models.DateTimeField(null=True, blank=True, db_column="ArchivadaEn")
    creada_en = models.DateTimeField(auto_now_add=True, db_column="CreadaEn")

    class Meta:
        db_table = "Notificaciones"
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"
        ordering = ["-creada_en", "-id"]
        indexes = [
            models.Index(fields=["usuario", "leida"], name="ix_notif_usuario_leida"),
            # La campana lista lo último de cada usuario en cada poll.
            models.Index(fields=["usuario", "-creada_en"], name="ix_notif_usr_fecha"),
        ]

    def __str__(self):
        return f"{self.titulo} → {self.usuario_id}"

    @property
    def sin_leer(self):
        return not self.leida

    def marcar_leida(self, commit=True):
        if self.leida:
            return
        self.leida = True
        self.leida_en = timezone.now()
        if commit:
            self.save(update_fields=["leida", "leida_en"])

    def marcar_mostrada(self, commit=True):
        """Evita que la ventana emergente vuelva a saltar."""
        if self.mostrada_en:
            return
        self.mostrada_en = timezone.now()
        if commit:
            self.save(update_fields=["mostrada_en"])

    @property
    def icono_tipo(self):
        """Icono alusivo por defecto según el tipo de aviso."""
        return {
            self.Tipo.BIENVENIDA: "i-star",
            self.Tipo.TICKET_NUEVO: "i-inbox",
            self.Tipo.TICKET_CERRADO: "i-check-circle",
            self.Tipo.TICKET_RECORDATORIO: "i-clock",
            self.Tipo.EVENTO: "i-calendar",
        }.get(self.tipo, "i-bell")
