import os

from django.conf import settings
from django.core.management.base import BaseCommand
from apps.accounts.models import Usuario


class Command(BaseCommand):
    help = (
        "Crea los usuarios iniciales del sistema. Las contraseñas se leen de "
        "variables de entorno (SEED_ADMIN_PASSWORD / SEED_USUARIO_PASSWORD). "
        "En producción se recomienda definir SEED_ADMIN_PASSWORD con un valor seguro."
    )

    def handle(self, *args, **options):
        debug = settings.DEBUG

        # Usuario administrador (staff/superuser)
        admin_email = os.getenv("SEED_ADMIN_EMAIL", "soporte@dogger.com.co").strip()
        admin_nombre = os.getenv("SEED_ADMIN_NOMBRE", "Ricardo Blandon").strip()
        admin_password = os.getenv("SEED_ADMIN_PASSWORD", "").strip()
        if debug and not admin_password:
            admin_password = "admin123"
        if not admin_password:
            self.stderr.write(
                self.style.ERROR(
                    "SEED_ADMIN_PASSWORD no definido y no estamos en DEBUG: no se crea el admin."
                )
            )
        elif not Usuario.objects.filter(email__iexact=admin_email).exists():
            user = Usuario.objects.create_superuser(
                email=admin_email, nombre=admin_nombre, password=admin_password
            )
            user.rol = Usuario.Rol.ADMIN
            user.is_staff = True
            user.is_superuser = True
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f"Admin creado: {admin_email} (password desde SEED_ADMIN_PASSWORD)")
            )
        else:
            self.stdout.write(f"Admin ya existe: {admin_email}")

        # Usuario de prueba (opcional, solo si definimos su email/password)
        usu_email = os.getenv("SEED_USUARIO_EMAIL", "jeralcom@gmail.com").strip()
        usu_nombre = os.getenv("SEED_USUARIO_NOMBRE", "Jeral Com").strip()
        usu_password = os.getenv("SEED_USUARIO_PASSWORD", "").strip()
        if not usu_password:
            self.stdout.write(self.style.WARNING("SEED_USUARIO_PASSWORD vacío: no se crea usuario de prueba."))
        elif Usuario.objects.filter(email__iexact=usu_email).exists():
            self.stdout.write(f"Usuario ya existe: {usu_email}")
        else:
            user = Usuario.objects.create_user(
                email=usu_email, nombre=usu_nombre, password=usu_password
            )
            user.rol = Usuario.Rol.USUARIO
            user.is_staff = False
            user.is_superuser = False
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f"Usuario creado: {usu_email} (password desde SEED_USUARIO_PASSWORD)")
            )
