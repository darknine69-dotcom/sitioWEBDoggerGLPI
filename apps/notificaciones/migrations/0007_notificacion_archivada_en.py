from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notificaciones", "0006_clavenotificacion")]
    operations = [migrations.AddField(model_name="notificacion", name="archivada_en", field=models.DateTimeField(blank=True, db_column="ArchivadaEn", null=True))]
