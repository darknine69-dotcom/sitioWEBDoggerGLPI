from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tickets", "0043_configsitio_horario_detalle")]
    operations = [migrations.AddField(model_name="configsitio", name="limites_inactividad", field=models.JSONField(blank=True, default=dict, verbose_name="Límites de inactividad en horas"))]
