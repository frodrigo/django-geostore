# Generated by Django 2.2.8 on 2019-12-16 12:27

from django.db import migrations
from geostore.db.schemas import schema_to_schemamodel
from django.apps import apps


def move_data(apps, schema_editor):
    # We can't import Layer models directly as it may be a newer
    # version than this migration expects. We use the historical version.
    Layer = apps.get_model('geostore', 'Layer')
    for layer in Layer.objects.all():
        schema_to_schemamodel(layer, layer.schema)


class Migration(migrations.Migration):

    dependencies = [
        ('geostore', '0038_merge_20191211_1306'),
    ]

    operations = [
        migrations.RunPython(move_data),
        migrations.RemoveField(
            model_name='layer',
            name='schema',
        ),
    ]
