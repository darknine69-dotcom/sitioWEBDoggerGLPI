from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.tickets.models import Ticket

User = get_user_model()

# Emails de usuarios de prueba creados por seed_prueba
EMAILS_PRUEBA = [
    "andres.moreno@dogger.com.co",
    "diana.rios@dogger.com.co",
    "julian.ospina@dogger.com.co",
    "laura.restrepo@dogger.com.co",
    "santiago.henao@dogger.com.co",
]


class Command(BaseCommand):
    help = "Elimina usuarios de prueba y sus tickets asociados"

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            help="Eliminar un usuario específico por email",
        )
        parser.add_argument(
            "--all-demo",
            action="store_true",
            help="Eliminar todos los usuarios de prueba conocidos",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="Listar todos los usuarios existentes",
        )

    def handle(self, *args, **options):
        if options["list"]:
            self._listar_usuarios()
            return

        if options["email"]:
            self._eliminar_usuario(options["email"])
            return

        if options["all_demo"]:
            eliminados = 0
            for email in EMAILS_PRUEBA:
                if self._eliminar_usuario(email, silent=True):
                    eliminados += 1
            self.stdout.write(
                self.style.SUCCESS(f"Usuarios de prueba eliminados: {eliminados}")
            )
            return

        self.stdout.write(self.style.WARNING(
            "Usa --all-demo para eliminar todos los de prueba, "
            "--email user@correo.com para uno específico, "
            "o --list para ver todos los usuarios."
        ))

    def _listar_usuarios(self):
        users = User.objects.all().order_by("rol", "nombre")
        self.stdout.write(f"\n{'Email':<40} {'Nombre':<25} {'Rol':<12} {'Activo'}")
        self.stdout.write("-" * 85)
        for u in users:
            self.stdout.write(
                f"{u.email:<40} {u.nombre:<25} {u.rol:<12} {'Si' if u.activo else 'No'}"
            )
        self.stdout.write(f"\nTotal: {users.count()} usuarios\n")

    def _eliminar_usuario(self, email, silent=False):
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            if not silent:
                self.stdout.write(self.style.WARNING(f"Usuario no encontrado: {email}"))
            return False

        # Eliminar tickets donde es solicitante
        tickets_solicitante = Ticket.objects.filter(solicitante_email=email).count()
        Ticket.objects.filter(solicitante_email=email).delete()

        # Desasignar tickets donde es técnico
        tickets_asignados = Ticket.objects.filter(tecnico_asignado=user).update(tecnico_asignado=None)

        nombre = user.nombre
        user.delete()

        if not silent:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Eliminado: {nombre} ({email}) · "
                    f"{tickets_solicitante} tickets eliminados · "
                    f"{tickets_asignados} tickets desasignados"
                )
            )
        return True
