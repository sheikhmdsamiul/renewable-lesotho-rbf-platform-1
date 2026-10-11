from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0056_report_export_formats'),
    ]

    operations = [
        migrations.AddField(
            model_name='installationreport',
            name='household_employment',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name='installationreport',
            name='household_income_level',
            field=models.CharField(blank=True, choices=[('no_income', 'No regular income'), ('low_income', 'Low income'), ('medium_income', 'Medium income'), ('high_income', 'High income')], max_length=32),
        ),
        migrations.AddField(
            model_name='installationreport',
            name='household_members',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='installationreport',
            name='female_members',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='installationreport',
            name='male_members',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]