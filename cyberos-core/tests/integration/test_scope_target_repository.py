from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cyberos.config.models import DatabaseSettings
from cyberos.core.errors import CyberOSError, ErrorCode
from cyberos.core.ids import new_id
from cyberos.domain.engagement.model import Engagement
from cyberos.domain.scope.model import Scope
from cyberos.domain.target.model import Target
from cyberos.domain.target.primitives import TargetKind, TargetRule, TargetStatus
from cyberos.domain.workspace.model import Workspace
from cyberos.persistence.connection import SQLiteConnectionFactory
from cyberos.persistence.engagement_repository import SQLiteEngagementRepository
from cyberos.persistence.migrations.runner import MigrationRunner
from cyberos.persistence.scope_repository import SQLiteScopeRepository
from cyberos.persistence.target_repository import SQLiteTargetRepository
from cyberos.persistence.unit_of_work import SQLiteUnitOfWork
from cyberos.persistence.workspace_repository import SQLiteWorkspaceRepository

MIGRATIONS_DIR = Path(__file__).parents[2] / "src/cyberos/persistence/migrations/versions"
NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def factory_for(tmp_path: Path) -> SQLiteConnectionFactory:
    factory = SQLiteConnectionFactory(DatabaseSettings(path=tmp_path / "cyberos.sqlite3"))
    MigrationRunner(factory, MIGRATIONS_DIR).run()
    return factory


def active_engagement(factory: SQLiteConnectionFactory) -> Engagement:
    workspace = Workspace.create("Repository Workspace", now=NOW)
    engagement = Engagement.create(workspace.id, "Repository Engagement", "learning", now=NOW)
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteWorkspaceRepository(unit).add(workspace)
        SQLiteEngagementRepository(unit).add(engagement)
        unit.commit()
    return engagement


def persist_scope(factory: SQLiteConnectionFactory, engagement: Engagement) -> Scope:
    scope = Scope.create(engagement.id, "API Scope", now=NOW)
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteScopeRepository(unit).add(scope)
        unit.commit()
    return scope


def fetch_scope(factory: SQLiteConnectionFactory, scope_id) -> Scope | None:
    with SQLiteUnitOfWork(factory) as unit:
        result = SQLiteScopeRepository(unit).get(scope_id)
        unit.rollback()
    return result


def fetch_target(factory: SQLiteConnectionFactory, target_id) -> Target | None:
    with SQLiteUnitOfWork(factory) as unit:
        result = SQLiteTargetRepository(unit).get(target_id)
        unit.rollback()
    return result


def test_scope_round_trip_and_list_by_engagement(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    engagement = active_engagement(factory)
    scope = persist_scope(factory, engagement)

    loaded = fetch_scope(factory, scope.id)
    with SQLiteUnitOfWork(factory) as unit:
        listed = SQLiteScopeRepository(unit).list_by_engagement(engagement.id)
        exists = SQLiteScopeRepository(unit).exists(scope.id)
        unit.rollback()

    assert loaded == scope
    assert listed == (scope,)
    assert exists is True
    assert loaded is not None
    assert loaded.id == scope.id
    assert loaded.engagement_id == engagement.id
    assert loaded.created_at == NOW
    assert loaded.updated_at == NOW
    assert loaded.targets == ()


def test_scope_update_archive_and_stale_version(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope = persist_scope(factory, active_engagement(factory))
    changed = scope.model_copy(
        update={"name": "Updated Scope", "updated_at": NOW + timedelta(minutes=1)}
    )

    with SQLiteUnitOfWork(factory) as unit:
        updated = SQLiteScopeRepository(unit).update(changed, expected_version=1)
        unit.commit()
    assert updated.name == "Updated Scope"
    assert updated.version == 2

    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as captured:
            SQLiteScopeRepository(unit).update(changed, expected_version=1)
        assert captured.value.code is ErrorCode.CONCURRENCY_CONFLICT
        unit.rollback()

    with SQLiteUnitOfWork(factory) as unit:
        archived = SQLiteScopeRepository(unit).archive(scope.id, expected_version=2)
        unit.commit()
    assert archived.status.value == "archived"
    assert archived.archived_at == archived.updated_at
    assert archived.version == 3


def test_scope_duplicate_and_missing_or_archived_engagement_errors(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    engagement = active_engagement(factory)
    persist_scope(factory, engagement)

    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as duplicate:
            SQLiteScopeRepository(unit).add(Scope.create(engagement.id, "API Scope", now=NOW))
        assert duplicate.value.code is ErrorCode.SCOPE_NAME_CONFLICT
        assert "sqlite" not in duplicate.value.message.lower()
        unit.rollback()

    missing = Scope.create(new_id(), "Missing Parent", now=NOW)
    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as missing_error:
            SQLiteScopeRepository(unit).add(missing)
        assert missing_error.value.code is ErrorCode.ENGAGEMENT_NOT_FOUND
        unit.rollback()

    with SQLiteUnitOfWork(factory) as unit:
        SQLiteEngagementRepository(unit).archive(engagement.id, expected_version=1)
        unit.commit()
    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as archived_error:
            SQLiteScopeRepository(unit).add(Scope.create(engagement.id, "Archived Parent", now=NOW))
        assert archived_error.value.code is ErrorCode.ENGAGEMENT_ARCHIVED
        unit.rollback()


def test_target_round_trip_list_update_archive_and_exists(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope = persist_scope(factory, active_engagement(factory))
    target = Target.create(
        scope.id, TargetRule.INCLUDE, TargetKind.FQDN, " API.EXAMPLE.COM. ", now=NOW
    )

    with SQLiteUnitOfWork(factory) as unit:
        SQLiteTargetRepository(unit).add(target)
        unit.commit()

    loaded = fetch_target(factory, target.id)
    with SQLiteUnitOfWork(factory) as unit:
        repository = SQLiteTargetRepository(unit)
        listed = repository.list_by_scope(scope.id)
        exists = repository.exists(target.id)
        unit.rollback()
    assert loaded == target
    assert listed == (target,)
    assert exists is True
    assert loaded is not None
    assert loaded.value == "api.example.com"
    assert loaded.created_at == NOW
    assert loaded.status is TargetStatus.ACTIVE

    changed = target.with_value("new.example.com", now=NOW + timedelta(minutes=1))
    with SQLiteUnitOfWork(factory) as unit:
        updated = SQLiteTargetRepository(unit).update(changed, expected_version=1)
        unit.commit()
    assert updated.value == "new.example.com"
    assert updated.version == 2

    with SQLiteUnitOfWork(factory) as unit:
        archived = SQLiteTargetRepository(unit).archive(target.id, expected_version=2)
        unit.commit()
    assert archived.status is TargetStatus.ARCHIVED
    assert archived.archived_at == archived.updated_at
    assert archived.version == 3


def test_target_duplicate_missing_parent_and_authorized_parent_guards(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope = persist_scope(factory, active_engagement(factory))
    target = Target.create(
        scope.id, TargetRule.EXCLUDE, TargetKind.URL, "https://example.com", now=NOW
    )
    with SQLiteUnitOfWork(factory) as unit:
        repository = SQLiteTargetRepository(unit)
        repository.add(target)
        with pytest.raises(CyberOSError) as duplicate:
            repository.add(target.model_copy(update={"id": new_id()}))
        assert duplicate.value.code is ErrorCode.TARGET_DUPLICATE
        assert "unique constraint" not in duplicate.value.message.lower()
        unit.rollback()

    missing = Target.create(
        new_id(), TargetRule.INCLUDE, TargetKind.FQDN, "missing.example.com", now=NOW
    )
    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as missing_error:
            SQLiteTargetRepository(unit).add(missing)
        assert missing_error.value.code is ErrorCode.SCOPE_NOT_FOUND
        unit.rollback()

    authorized = scope.mark_validated(at=NOW).authorize("approval", at=NOW + timedelta(minutes=1))
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteScopeRepository(unit).update(authorized, expected_version=1)
        unit.commit()
    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as immutable:
            SQLiteTargetRepository(unit).add(
                Target.create(
                    scope.id, TargetRule.INCLUDE, TargetKind.FQDN, "admin.example.com", now=NOW
                )
            )
        assert immutable.value.code is ErrorCode.AUTHORIZED_SCOPE_IMMUTABLE
        unit.rollback()


def test_target_stale_version_and_scope_fk_protection(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope = persist_scope(factory, active_engagement(factory))
    target = Target.create(scope.id, TargetRule.INCLUDE, TargetKind.IPV4, "10.0.0.8", now=NOW)
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteTargetRepository(unit).add(target)
        unit.commit()
    changed = target.with_value("10.0.0.9", now=NOW + timedelta(minutes=1))
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteTargetRepository(unit).update(changed, expected_version=1)
        unit.commit()
    with SQLiteUnitOfWork(factory) as unit:
        with pytest.raises(CyberOSError) as captured:
            SQLiteTargetRepository(unit).update(target, expected_version=1)
        assert captured.value.code is ErrorCode.CONCURRENCY_CONFLICT
        unit.rollback()


def test_repository_exception_rolls_back_scope_and_target_changes(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    engagement = active_engagement(factory)
    scope = Scope.create(engagement.id, "Rollback Scope", now=NOW)
    target = Target.create(
        scope.id, TargetRule.INCLUDE, TargetKind.FQDN, "rollback.example.com", now=NOW
    )

    with pytest.raises(RuntimeError, match="force rollback"):
        with SQLiteUnitOfWork(factory) as unit:
            SQLiteScopeRepository(unit).add(scope)
            SQLiteTargetRepository(unit).add(target)
            raise RuntimeError("force rollback")

    assert fetch_scope(factory, scope.id) is None
    assert fetch_target(factory, target.id) is None


def test_repositories_never_return_sqlite_rows(tmp_path: Path) -> None:
    factory = factory_for(tmp_path)
    scope = persist_scope(factory, active_engagement(factory))
    target = Target.create(
        scope.id, TargetRule.INCLUDE, TargetKind.FQDN, "rows.example.com", now=NOW
    )
    with SQLiteUnitOfWork(factory) as unit:
        SQLiteTargetRepository(unit).add(target)
        loaded_scope = SQLiteScopeRepository(unit).get(scope.id)
        loaded_target = SQLiteTargetRepository(unit).get(target.id)
        unit.rollback()
    assert isinstance(loaded_scope, Scope)
    assert isinstance(loaded_target, Target)
