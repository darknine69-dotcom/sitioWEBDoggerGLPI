from django.http import HttpResponse
from apps.accounts.models import Usuario


def seed_usuarios_view(request):
    resultados = []

    usuarios = [
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

    for data in usuarios:
        if Usuario.objects.filter(email=data["email"]).exists():
            resultados.append(f"Ya existe: {data['email']}")
            continue
        if data["is_superuser"]:
            user = Usuario.objects.create_superuser(
                email=data["email"],
                nombre=data["nombre"],
                password=data["password"],
            )
        else:
            user = Usuario.objects.create_user(
                email=data["email"],
                nombre=data["nombre"],
                password=data["password"],
            )
        user.rol = data["rol"]
        user.is_staff = data["is_staff"]
        user.is_superuser = data["is_superuser"]
        user.save()
        resultados.append(f"Creado: {data['email']} / {data['password']}")

    html = "<h1>Seed Usuarios</h1><ul>" + "".join(f"<li>{r}</li>" for r in resultados) + "</ul>"
    return HttpResponse(html)


def seed_categorias_view(request):
    import io, sys
    from django.core.management import call_command

    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    call_command("seed_categorias")
    sys.stdout = old_stdout
    return HttpResponse(f"<h1>Seed Categorias</h1><pre>{buf.getvalue()}</pre>")


def seed_prueba_view(request):
    import io, sys
    from django.core.management import call_command

    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    call_command("seed_prueba")
    sys.stdout = old_stdout
    return HttpResponse(f"<h1>Seed Tickets de Prueba</h1><pre>{buf.getvalue()}</pre>")
