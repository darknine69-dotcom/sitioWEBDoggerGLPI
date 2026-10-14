"""
Lista todos los usuarios existentes en la base de datos.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Lista todos los usuarios en la base de datos"

    def handle(self, *args, **options):
        usuarios = User.objects.all().order_by("email")
        count = usuarios.count()

        if count == 0:
            self.stdout.write(self.style.WARNING("No hay usuarios en la base de datos."))
            return

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"  {count} usuario(s) en la base de datos")
        self.stdout.write(f"{'='*60}\n")

        for u in usuarios:
            estado = "✓" if u.is_active else "✗"
            self.stdout.write(
                f"  {estado} {u.email:<35} | {u.nombre:<25} | rol={u.rol}"
            )

        self.stdout.write(f"\n{'='*60}\n")
