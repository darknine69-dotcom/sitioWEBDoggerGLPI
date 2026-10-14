"""
Management command para resetear las contraseñas de todos los usuarios.

Uso:
    python manage.py reset_passwords --password "NuevaClave2026*"
    python manage.py reset_passwords --password "NuevaClave2026*" --email admin@dogger.com.co
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Resetea las contraseñas de los usuarios"

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            type=str,
            required=True,
            help="Nueva contraseña para los usuarios",
        )
        parser.add_argument(
            "--email",
            type=str,
            required=False,
            help="Si se especifica, solo resetea la contraseña de ese usuario",
        )

    def handle(self, *args, **options):
        nueva_password = options["password"]
        email_filtro = options.get("email")

        if email_filtro:
            usuarios = User.objects.filter(email__iexact=email_filtro)
        else:
            usuarios = User.objects.all()

        count = usuarios.count()
        if count == 0:
            self.stdout.write(self.style.WARNING("No se encontraron usuarios."))
            return

        self.stdout.write(f"Reseteando contraseñas de {count} usuario(s)...")

        for usuario in usuarios:
            usuario.set_password(nueva_password)
            usuario.is_active = True
            usuario.activo = True
            usuario.save(update_fields=["password", "is_active", "activo"])
            self.stdout.write(f"  ✓ {usuario.email}")

        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Se resetearon {count} contraseña(s) a: {nueva_password}"
        ))
