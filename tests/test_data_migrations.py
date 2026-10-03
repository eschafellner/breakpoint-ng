import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_sepa_data_migration_encrypts_legacy_values_and_is_reversible():
    previous = ("members", "0001_initial")
    target = ("members", "0002_alter_membershipapplication_sepa_iban")
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([previous])
        state = executor.loader.project_state([previous]).apps
        User = state.get_model("accounts", "User")
        Type = state.get_model("members", "MembershipType")
        Application = state.get_model("members", "MembershipApplication")
        user = User.objects.create(email="legacy@example.com")
        membership_type = Type.objects.create(name="Legacy")
        application = Application.objects.create(
            user=user, requested_type=membership_type, sepa_iban="AT1234567890"
        )
        executor = MigrationExecutor(connection)
        executor.migrate([target])
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT sepa_iban FROM members_membershipapplication WHERE id = %s",
                [application.pk],
            )
            assert cursor.fetchone()[0].startswith("fernet:")
        Application = executor.loader.project_state([target]).apps.get_model(
            "members", "MembershipApplication"
        )
        assert Application.objects.get(pk=application.pk).sepa_iban == "AT1234567890"
        executor = MigrationExecutor(connection)
        executor.migrate([previous])
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT sepa_iban FROM members_membershipapplication WHERE id = %s",
                [application.pk],
            )
            assert cursor.fetchone()[0] == "AT1234567890"
    finally:
        MigrationExecutor(connection).migrate(latest)


@pytest.mark.django_db(transaction=True)
def test_email_constraint_migration_rejects_existing_case_duplicates():
    previous = ("accounts", "0002_create_groups")
    target = ("accounts", "0003_user_last_failed_login_at_and_more")
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    duplicate = None
    User = None
    try:
        executor.migrate([previous])
        User = executor.loader.project_state([previous]).apps.get_model(
            "accounts", "User"
        )
        User.objects.create(email="duplicate@example.com")
        duplicate = User.objects.create(email="DUPLICATE@example.com")
        with pytest.raises(RuntimeError, match="mehrfach vorhanden"):
            MigrationExecutor(connection).migrate([target])
    finally:
        if duplicate is not None:
            User.objects.filter(pk=duplicate.pk).delete()
        MigrationExecutor(connection).migrate(latest)
