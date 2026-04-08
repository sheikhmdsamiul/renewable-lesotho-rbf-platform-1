from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0019_project_setup_meter_kpi_fields'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE projects_project "
                        "ADD COLUMN IF NOT EXISTS installation_target_summary varchar(255) NOT NULL DEFAULT '';"
                        "ALTER TABLE projects_project "
                        "ADD COLUMN IF NOT EXISTS project_duration_months integer NOT NULL DEFAULT 0;"
                        "ALTER TABLE projects_project "
                        "ADD COLUMN IF NOT EXISTS target_low_income_pct integer NOT NULL DEFAULT 0;"
                        "ALTER TABLE projects_project "
                        "ADD COLUMN IF NOT EXISTS verification_method varchar(255) NOT NULL DEFAULT '';"
                    ),
                    reverse_sql=(
                        "ALTER TABLE projects_project DROP COLUMN IF EXISTS verification_method;"
                        "ALTER TABLE projects_project DROP COLUMN IF EXISTS target_low_income_pct;"
                        "ALTER TABLE projects_project DROP COLUMN IF EXISTS project_duration_months;"
                        "ALTER TABLE projects_project DROP COLUMN IF EXISTS installation_target_summary;"
                    ),
                ),
            ],
            state_operations=[],
        ),
    ]
