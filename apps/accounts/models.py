from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


def avatar_upload_to(instance, filename):
    import uuid
    from pathlib import Path
    ext = Path(filename).suffix.lower() or ".jpg"
    return f"avatars/{instance.pk or 'tmp'}/{uuid.uuid4().hex}{ext}"


class UsuarioManager(BaseUserManager):
    def create_user(self, email, nombre, password=None, **extra):
        if not email:
            raise ValueError("El correo es obligatorio")
        email = self.normalize_email(email)
        # Mantener sincronizados los flags de "activo" (app) e "is_active" (auth Django):
        # el login de Django usa is_active, y la vista/permisos leen activo.
        if "activo" in extra and "is_active" not in extra:
            extra["is_active"] = bool(extra["activo"])
        user = self.model(email=email, nombre=nombre, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, nombre, password=None, **extra):
        extra.setdefault("rol", "admin")
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, nombre, password, **extra)


class Usuario(AbstractBaseUser, PermissionsMixin):
    class Rol(models.TextChoices):
        ADMIN = "admin", "Administrador"
        TECNICO = "tecnico", "Técnico"
        USUARIO = "usuario", "Usuario"

    nombre = models.CharField("Nombre", max_length=100)
    email = models.EmailField("Correo", max_length=150, unique=True)
    telefono = models.CharField("Teléfono", max_length=20, blank=True, default="")
    avatar = models.ImageField("Foto de perfil", upload_to=avatar_upload_to, blank=True, null=True)

    class Genero(models.TextChoices):
        MASCULINO = "masculino", "Masculino"
        FEMENINO = "femenino", "Femenino"

    genero = models.CharField(
        "Género",
        max_length=20,
        choices=Genero.choices,
        default=Genero.MASCULINO,
    )
    rol = models.CharField(
        max_length=20,
        choices=Rol.choices,
        default=Rol.TECNICO,
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    glpi_user_id = models.PositiveIntegerField(
        "ID usuario GLPI",
        null=True,
        blank=True,
        help_text="ID del técnico en GLPI para sincronizar asignaciones",
    )

    # Campos requeridos por Django admin / PermissionsMixin
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nombre"]

    class Meta:
        db_table = "Usuarios"
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} <{self.email}>"

    @property
    def es_staff_helpdesk(self):
        """Admin o técnico pueden gestionar tickets."""
        return self.rol in (self.Rol.ADMIN, self.Rol.TECNICO) and self.is_active

    @property
    def initials(self):
        parts = (self.nombre or "").strip().split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return (self.nombre or "?")[:2].upper()


class ResetPasswordToken(models.Model):
    """Código de un solo uso para restablecer la contraseña olvidada."""
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="reset_tokens",
        db_column="UsuarioId",
    )
    codigo = models.CharField("Código", max_length=6)
    creado = models.DateTimeField(auto_now_add=True)
    usado = models.BooleanField(default=False)

    class Meta:
        db_table = "ResetPasswordTokens"
        verbose_name = "Token de restablecimiento"
        verbose_name_plural = "Tokens de restablecimiento"
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.codigo} — {self.usuario.email}"

    @classmethod
    def generar(cls, usuario):
        import secrets

        cls.objects.filter(usuario=usuario, usado=False).delete()
        return cls.objects.create(
            usuario=usuario,
            codigo=str(secrets.randbelow(1000000)).zfill(6),
        )

    @property
    def expirado(self):
        # 30 minutos de vigencia
        return (timezone.now() - self.creado).total_seconds() > 1800
