from django.core.management.base import BaseCommand
from apps.accounts.models import Usuario


USUARIOS = [
    {
        "email": "soporte@dogger.com.co",
        "nombre": "Ricardo Blandon",
        "password": "admin123",
        "rol": "admin",
        "is_staff": True,
        "is_superuser": True,
    },
    {
        "email": "jeralcom@gmail.com",
        "nombre": "Jeral Com",
        "password": "clave123",
        "rol": "usuario",
        "is_staff": False,
        "is_superuser": False,
    },
]


class Command(BaseCommand):
    help = "Crea los usuarios iniciales del sistema"

    def handle(self, *args, **options):
        for data in USUARIOS:
            if Usuario.objects.filter(email=data["email"]).exists():
                self.stdout.write(f"Ya existe: {data['email']}")
                continue
            user = Usuario.objects.create_superuser(
                email=data["email"],
                nombre=data["nombre"],
                password=data["password"],
            ) if data["is_superuser"] else Usuario.objects.create_user(
                email=data["email"],
                nombre=data["nombre"],
                password=data["password"],
            )
            user.rol = data["rol"]
            user.is_staff = data["is_staff"]
            user.is_superuser = data["is_superuser"]
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Creado: {data['email']} / {data['password']}"))
