import apps.businesses.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("businesses", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="business",
            name="timezone",
            field=models.CharField(
                default="UTC",
                max_length=64,
                validators=[apps.businesses.validators.validate_iana_timezone],
            ),
        ),
    ]
