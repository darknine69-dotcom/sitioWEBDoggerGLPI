# La casilla que el administrador enciende para que la persona pueda cambiar
# de rol desde su propia barra superior, en cualquier vista.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0018_alter_usuario_rol'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuario',
            name='cambio_rol_habilitado',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Si está activo, esa persona ve un botón «Cambiar rol» junto a su '
                    'nombre en la barra superior de cualquier vista y puede pasar a otro '
                    'rol sin que el administrador tenga que editar la ficha.'
                ),
                verbose_name='Puede cambiar de rol',
            ),
        ),
    ]
