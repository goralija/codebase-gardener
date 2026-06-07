import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("maintenance_prs", "0006_maintenanceprplan_outcome_history_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="maintenanceprplan",
            name="confidence_threshold",
            field=models.FloatField(
                default=0.85,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(1),
                ],
            ),
        ),
    ]
