from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tickets", "0044_configsitio_limites_inactividad")]
    operations = [migrations.AddField(model_name="configsitio", name="escalamiento_inactividad", field=models.JSONField(blank=True, default=dict, verbose_name="Escalamiento de inactividad"))]
