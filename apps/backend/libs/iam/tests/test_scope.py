import pytest
from iam.application.policy import ensure_group_assignment, ensure_resource_access

from iam import AccessScope, ActiveUserData, ForbiddenError, Role


def test_admin_can_access_any_owner_and_group() -> None:
    scope = AccessScope(user_id=1, group_ids=frozenset(), is_admin=True)

    assert scope.can_access(owner_id=99, group_id=None) is True
    assert scope.can_access(owner_id=99, group_id=7) is True
    assert scope.can_assign_group(7) is True


def test_owner_can_access_a_personal_resource() -> None:
    scope = AccessScope(user_id=10, group_ids=frozenset({5}))

    assert scope.can_access(owner_id=10, group_id=None) is True
    assert scope.can_access(owner_id=20, group_id=None) is False


def test_group_member_can_access_that_group_only() -> None:
    scope = AccessScope(user_id=30, group_ids=frozenset({5}))

    assert scope.can_access(owner_id=10, group_id=5) is True
    assert scope.can_access(owner_id=10, group_id=9) is False
    assert scope.can_access(owner_id=10, group_id=None) is False


def test_assignment_allows_personal_or_member_group() -> None:
    scope = AccessScope(user_id=10, group_ids=frozenset({5}))

    assert scope.can_assign_group(None) is True
    assert scope.can_assign_group(5) is True
    assert scope.can_assign_group(9) is False


def test_active_user_projects_an_access_scope() -> None:
    user = ActiveUserData(
        sub=10,
        email="a@example.com",
        role=Role.REGULAR,
        group_ids=frozenset({5, 1}),
    )

    assert user.is_admin is False
    assert user.to_access_scope() == AccessScope(
        user_id=10,
        group_ids=frozenset({5, 1}),
        is_admin=False,
    )


def test_ensure_resource_access_rejects_an_outsider() -> None:
    scope = AccessScope(user_id=20, group_ids=frozenset({9}))

    with pytest.raises(ForbiddenError, match="building"):
        ensure_resource_access(scope, owner_id=10, group_id=5, resource_name="building")


def test_ensure_group_assignment_rejects_a_foreign_group() -> None:
    scope = AccessScope(user_id=10, group_ids=frozenset({5}))

    with pytest.raises(ForbiddenError, match="group you do not belong to"):
        ensure_group_assignment(scope, 9)

    ensure_group_assignment(scope, None)
    ensure_group_assignment(scope, 5)
