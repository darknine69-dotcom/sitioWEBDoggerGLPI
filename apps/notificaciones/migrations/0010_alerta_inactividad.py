from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notificaciones", "0009_alerta_preservacion")]
    operations = [
        migrations.AddField(model_name="alertaoperativa", name="ultima_actividad_en", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="alertaoperativa", name="inactividad_segundos", field=models.PositiveIntegerField(blank=True, null=True)),
    ]
