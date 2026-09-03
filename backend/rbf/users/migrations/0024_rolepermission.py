from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0023_platformconfiguration_contact_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='RolePermission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[
                    ('RBF Management Team', 'RBF Management Team'),
                    ('TAC Member', 'TAC Member'),
                    ('DoE Officer', 'DoE Officer'),
                    ('Field Verifier', 'Field Verifier'),
                    ('Vendor', 'Vendor'),
                    ('Platform Administrator (Super Admin)', 'Platform Administrator (Super Admin)'),
                    ('Project Steering Committee', 'Project Steering Committee'),
                    ('Auditor', 'Auditor'),
                ], max_length=64)),
                ('module', models.CharField(max_length=64)),
                ('actions', models.JSONField(blank=True, default=list)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['role', 'module']},
        ),
        migrations.AddConstraint(
            model_name='rolepermission',
            constraint=models.UniqueConstraint(fields=('role', 'module'), name='unique_role_permission_module'),
        ),
    ]
