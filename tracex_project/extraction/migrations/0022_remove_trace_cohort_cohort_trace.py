# Generated by Django 4.2.11 on 2024-05-09 21:28

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("extraction", "0021_alter_event_event_type_alter_event_location_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="trace",
            name="cohort",
        ),
        migrations.AddField(
            model_name="cohort",
            name="trace",
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="cohort",
                to="extraction.trace",
            ),
        ),
    ]