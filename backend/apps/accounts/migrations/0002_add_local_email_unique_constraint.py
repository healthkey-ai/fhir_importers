import apps.accounts.models
import django.utils.timezone
from django.db import connection, migrations, models


def create_identity_table_if_missing(apps, schema_editor):
    """Create the identity table for databases that have the old User-based 0001_initial."""
    table_names = connection.introspection.table_names()
    if "identity" in table_names:
        return

    schema_editor.execute("""
        CREATE TABLE "identity" (
            "id" bigserial NOT NULL PRIMARY KEY,
            "password" varchar(128) NOT NULL,
            "last_login" timestamp with time zone NULL,
            "is_superuser" boolean NOT NULL,
            "issuer" varchar(255) NOT NULL,
            "sub" varchar(255) NOT NULL UNIQUE,
            "email" varchar(254) NOT NULL,
            "name" varchar(255) NOT NULL,
            "is_active" boolean NOT NULL,
            "is_staff" boolean NOT NULL,
            "created_at" timestamp with time zone NOT NULL
        )
    """)
    schema_editor.execute("""
        CREATE TABLE "identity_groups" (
            "id" bigserial NOT NULL PRIMARY KEY,
            "identity_id" bigint NOT NULL REFERENCES "identity" ("id") DEFERRABLE INITIALLY DEFERRED,
            "group_id" integer NOT NULL REFERENCES "auth_group" ("id") DEFERRABLE INITIALLY DEFERRED,
            UNIQUE ("identity_id", "group_id")
        )
    """)
    schema_editor.execute("""
        CREATE TABLE "identity_user_permissions" (
            "id" bigserial NOT NULL PRIMARY KEY,
            "identity_id" bigint NOT NULL REFERENCES "identity" ("id") DEFERRABLE INITIALLY DEFERRED,
            "permission_id" integer NOT NULL REFERENCES "auth_permission" ("id") DEFERRABLE INITIALLY DEFERRED,
            UNIQUE ("identity_id", "permission_id")
        )
    """)
    schema_editor.execute("""
        ALTER TABLE "identity"
        ADD CONSTRAINT "uq_identity_issuer_sub" UNIQUE ("issuer", "sub")
    """)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_identity_table_if_missing, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="identity",
            constraint=models.UniqueConstraint(
                condition=models.Q(("issuer", "urn:local"), models.Q(("email", ""), _negated=True)),
                fields=("email",),
                name="uq_identity_local_email",
            ),
        ),
    ]
