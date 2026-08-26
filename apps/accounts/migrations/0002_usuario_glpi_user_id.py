from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="glpi_user_id",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="ID del técnico en GLPI para sincronizar asignaciones",
                null=True,
                verbose_name="ID usuario GLPI",
            ),
        ),
    ]
