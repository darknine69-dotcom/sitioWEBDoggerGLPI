from django.db import migrations, models
import apps.accounts.models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_usuario_glpi_user_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuario',
            name='telefono',
            field=models.CharField(blank=True, default='', max_length=20, verbose_name='Teléfono'),
        ),
        migrations.AddField(
            model_name='usuario',
            name='avatar',
            field=models.ImageField(blank=True, null=True, upload_to=apps.accounts.models.avatar_upload_to, verbose_name='Foto de perfil'),
        ),
    ]
