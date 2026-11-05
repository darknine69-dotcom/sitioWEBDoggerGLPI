from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tickets", "0042_tarea_diferida")]
    operations = [migrations.AddField(model_name="configsitio", name="horario_detalle", field=models.JSONField(blank=True, default=None, null=True, verbose_name="Horario de atención publicado"))]
