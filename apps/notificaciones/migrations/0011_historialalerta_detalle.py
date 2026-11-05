from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notificaciones", "0010_alerta_inactividad")]
    operations = [migrations.AddField(model_name="historialalerta", name="detalle", field=models.CharField(blank=True, default="", max_length=500))]
