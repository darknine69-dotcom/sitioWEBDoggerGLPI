from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tickets", "0052_decisionautoasignacion_categoria_nombre")]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="asignacion_manual_protegida",
            field=models.BooleanField(
                default=False, editable=False,
                help_text="Impide que el motor anule una decisión manual, incluso si deja el ticket sin técnico.",
            ),
        ),
    ]
