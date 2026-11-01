from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0023_usuario_preferencias_notificaciones")]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="horario_atencion",
            field=models.CharField(blank=True, default="", max_length=120, verbose_name="Horario de atención"),
        ),
    ]
