"""Tests for the account listing and both password changes, written from
openspec/changes/add-mcp-user-management/specs/user-management.

The privilege rules, the fields the listing must never disclose, and token invalidation are
each asserted directly rather than incidentally through a success path: they are the reasons
these endpoints are safe to expose, so a test that only ever saw them work would prove nothing.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from embargo.models import AccountCountry

LIST_URL = '/api/users/'
SELF_URL = '/api/me/change-password/'
OLD_PASSWORD = 'lovelace1'
NEW_PASSWORD = 'babbage22'


def admin_url(username):
    return f'/api/users/{username}/change-password/'


def token_for(user):
    token, _ = Token.objects.get_or_create(user=user)
    return token


def as_user(client, user):
    client.credentials(HTTP_AUTHORIZATION=f'Token {token_for(user).key}')
    return client


@pytest.fixture
def administrator(db):
    return User.objects.create_user(
        username='grace', email='grace@example.com', password=OLD_PASSWORD, is_staff=True
    )


@pytest.fixture
def member(db):
    user = User.objects.create_user(
        username='ada', email='ada@example.com', password=OLD_PASSWORD
    )
    AccountCountry.objects.create(user=user, country='pakistan')
    return user


@pytest.fixture
def other_member(db):
    user = User.objects.create_user(
        username='alan', email='alan@example.com', password=OLD_PASSWORD
    )
    AccountCountry.objects.create(user=user, country='united kingdom')
    return user


# --- Requirement: List accounts --------------------------------------------------------------


@pytest.mark.django_db
def test_an_administrator_receives_every_account_with_its_country_and_signup_date(
    client, administrator, member, other_member
):
    response = as_user(client, administrator).get(LIST_URL)

    assert response.status_code == 200
    assert {entry['username'] for entry in response.data} == {'grace', 'ada', 'alan'}
    ada = next(e for e in response.data if e['username'] == 'ada')
    assert ada['country'] == 'pakistan'
    assert ada['date_joined']


# --- Requirement: Require administrative privileges to list accounts -------------------------


@pytest.mark.django_db
def test_an_unauthenticated_caller_cannot_list_accounts(client, administrator, member):
    response = client.get(LIST_URL)

    assert response.status_code == 401
    assert 'ada' not in response.content.decode()


@pytest.mark.django_db
def test_an_authenticated_non_administrator_cannot_list_accounts(client, administrator, member):
    response = as_user(client, member).get(LIST_URL)

    assert response.status_code == 403
    assert 'grace' not in response.content.decode()


# --- Requirement: Filter the account listing by country --------------------------------------


@pytest.mark.django_db
def test_filtering_by_country_returns_only_those_accounts(
    client, administrator, member, other_member
):
    response = as_user(client, administrator).get(LIST_URL, {'country': 'pakistan'})

    assert {entry['username'] for entry in response.data} == {'ada'}


@pytest.mark.django_db
def test_a_country_differing_only_in_case_returns_the_same_accounts(
    client, administrator, member, other_member
):
    response = as_user(client, administrator).get(LIST_URL, {'country': 'PaKiStAn'})

    assert {entry['username'] for entry in response.data} == {'ada'}


# --- Requirement: Filter the account listing by username -------------------------------------


@pytest.mark.django_db
def test_filtering_by_username_returns_only_that_account(
    client, administrator, member, other_member
):
    response = as_user(client, administrator).get(LIST_URL, {'username': 'alan'})

    assert {entry['username'] for entry in response.data} == {'alan'}


@pytest.mark.django_db
def test_a_username_differing_only_in_case_returns_the_same_account(
    client, administrator, member, other_member
):
    response = as_user(client, administrator).get(LIST_URL, {'username': 'AlAn'})

    assert {entry['username'] for entry in response.data} == {'alan'}


# --- Requirement: Include accounts with no recorded country ----------------------------------


@pytest.mark.django_db
def test_an_account_created_outside_signup_appears_with_an_empty_country(
    client, administrator, member
):
    """`administrator` is made directly, the way createsuperuser makes one - no country row.

    It still has to appear: an administrative listing that quietly omitted accounts would
    misrepresent who exists on the system.
    """
    response = as_user(client, administrator).get(LIST_URL)

    entry = next(e for e in response.data if e['username'] == 'grace')
    assert entry['country'] is None


# --- Requirement: Never disclose an email address or an internal identifier in a listing -----


@pytest.mark.django_db
def test_an_unfiltered_listing_discloses_no_address_and_no_identifier(
    client, administrator, member
):
    response = as_user(client, administrator).get(LIST_URL)

    body = response.content.decode()
    assert 'ada@example.com' not in body
    assert 'grace@example.com' not in body
    for entry in response.data:
        assert set(entry) == {'username', 'country', 'date_joined'}


@pytest.mark.django_db
def test_a_filtered_listing_discloses_no_address_and_no_identifier(
    client, administrator, member
):
    response = as_user(client, administrator).get(LIST_URL, {'country': 'pakistan'})

    body = response.content.decode()
    assert 'ada@example.com' not in body
    for entry in response.data:
        assert set(entry) == {'username', 'country', 'date_joined'}


# --- Requirement: Change any account's password as an administrator --------------------------


@pytest.mark.django_db
def test_an_administrator_changes_another_accounts_password(client, administrator, member):
    response = as_user(client, administrator).post(
        admin_url('ada'), {'password': NEW_PASSWORD}, format='json'
    )

    assert response.status_code == 200
    member.refresh_from_db()
    assert member.check_password(NEW_PASSWORD)
    assert not member.check_password(OLD_PASSWORD)


# --- Requirement: Require administrative privileges to change another account's password -----


@pytest.mark.django_db
def test_a_non_administrator_cannot_change_another_accounts_password(
    client, administrator, member
):
    response = as_user(client, member).post(
        admin_url('grace'), {'password': NEW_PASSWORD}, format='json'
    )

    assert response.status_code == 403
    administrator.refresh_from_db()
    assert administrator.check_password(OLD_PASSWORD)


@pytest.mark.django_db
def test_an_unauthenticated_caller_cannot_change_another_accounts_password(
    client, administrator, member
):
    response = client.post(admin_url('ada'), {'password': NEW_PASSWORD}, format='json')

    assert response.status_code == 401
    member.refresh_from_db()
    assert member.check_password(OLD_PASSWORD)


# --- Requirement: Resolve the named account without regard to case ---------------------------


@pytest.mark.django_db
def test_an_account_named_in_a_different_case_is_still_found(client, administrator, member):
    response = as_user(client, administrator).post(
        admin_url('AdA'), {'password': NEW_PASSWORD}, format='json'
    )

    assert response.status_code == 200
    member.refresh_from_db()
    assert member.check_password(NEW_PASSWORD)


@pytest.mark.django_db
def test_a_name_matching_more_than_one_account_changes_nothing(client, administrator, member):
    """Django's uniqueness on username is case-sensitive, so these two can coexist.

    Choosing between them would change a password on an account the caller did not name.
    """
    twin = User.objects.create_user(
        username='Ada', email='ada.twin@example.com', password=OLD_PASSWORD
    )

    response = as_user(client, administrator).post(
        admin_url('ada'), {'password': NEW_PASSWORD}, format='json'
    )

    assert response.status_code == 400
    member.refresh_from_db()
    twin.refresh_from_db()
    assert member.check_password(OLD_PASSWORD)
    assert twin.check_password(OLD_PASSWORD)


# --- Requirement: Reject a password change for an unknown account ----------------------------


@pytest.mark.django_db
def test_changing_the_password_of_an_unknown_account_is_refused(client, administrator):
    response = as_user(client, administrator).post(
        admin_url('nobody'), {'password': NEW_PASSWORD}, format='json'
    )

    assert response.status_code == 404


# --- Requirement: Change one's own password --------------------------------------------------


@pytest.mark.django_db
def test_a_caller_changes_their_own_password(client, member):
    response = as_user(client, member).post(
        SELF_URL,
        {'current_password': OLD_PASSWORD, 'new_password': NEW_PASSWORD},
        format='json',
    )

    assert response.status_code == 200
    member.refresh_from_db()
    assert member.check_password(NEW_PASSWORD)
    assert not member.check_password(OLD_PASSWORD)


@pytest.mark.django_db
def test_an_unauthenticated_caller_cannot_change_their_own_password(client, member):
    response = client.post(
        SELF_URL,
        {'current_password': OLD_PASSWORD, 'new_password': NEW_PASSWORD},
        format='json',
    )

    assert response.status_code == 401
    member.refresh_from_db()
    assert member.check_password(OLD_PASSWORD)


# --- Requirement: Refuse a self-service change without the correct current password ----------


@pytest.mark.django_db
def test_a_wrong_current_password_changes_nothing(client, member):
    """A valid token alone must not be enough.

    If it were, a stolen token would be account takeover, and the token invalidation that
    exists to contain a stolen token would be defeated by that very token.
    """
    response = as_user(client, member).post(
        SELF_URL,
        {'current_password': 'not-the-password1', 'new_password': NEW_PASSWORD},
        format='json',
    )

    assert response.status_code == 400
    member.refresh_from_db()
    assert member.check_password(OLD_PASSWORD)


# --- Requirement: Hold a changed password to the signup strength rules -----------------------


@pytest.mark.django_db
@pytest.mark.parametrize('weak', ['abc123', 'noDigitsHere', '12345678'])
def test_an_administrative_change_refuses_a_password_signup_would_refuse(
    client, administrator, member, weak
):
    response = as_user(client, administrator).post(
        admin_url('ada'), {'password': weak}, format='json'
    )

    assert response.status_code == 400
    member.refresh_from_db()
    assert member.check_password(OLD_PASSWORD)


@pytest.mark.django_db
@pytest.mark.parametrize('weak', ['abc123', 'noDigitsHere', '12345678'])
def test_a_self_service_change_refuses_a_password_signup_would_refuse(client, member, weak):
    response = as_user(client, member).post(
        SELF_URL,
        {'current_password': OLD_PASSWORD, 'new_password': weak},
        format='json',
    )

    assert response.status_code == 400
    member.refresh_from_db()
    assert member.check_password(OLD_PASSWORD)


@pytest.mark.django_db
def test_an_administrative_change_refuses_a_password_above_the_maximum(
    client, administrator, member
):
    response = as_user(client, administrator).post(
        admin_url('ada'), {'password': 'a1' + 'x' * 127}, format='json'
    )

    assert response.status_code == 400
    assert 'at most 128' in str(response.data)
    member.refresh_from_db()
    assert member.check_password(OLD_PASSWORD)


@pytest.mark.django_db
def test_a_self_service_change_refuses_a_password_above_the_maximum(client, member):
    response = as_user(client, member).post(
        SELF_URL,
        {'current_password': OLD_PASSWORD, 'new_password': 'a1' + 'x' * 127},
        format='json',
    )

    assert response.status_code == 400
    assert 'at most 128' in str(response.data)
    member.refresh_from_db()
    assert member.check_password(OLD_PASSWORD)


# --- Requirement: Invalidate existing authentication tokens on a password change -------------


@pytest.mark.django_db
def test_an_administrative_change_invalidates_the_targets_token(client, administrator, member):
    stale = token_for(member).key

    as_user(client, administrator).post(
        admin_url('ada'), {'password': NEW_PASSWORD}, format='json'
    )

    client.credentials(HTTP_AUTHORIZATION=f'Token {stale}')
    assert client.get(LIST_URL).status_code == 401


@pytest.mark.django_db
def test_a_self_service_change_invalidates_the_callers_own_token(client, member):
    stale = token_for(member).key

    response = as_user(client, member).post(
        SELF_URL,
        {'current_password': OLD_PASSWORD, 'new_password': NEW_PASSWORD},
        format='json',
    )
    assert response.status_code == 200

    client.credentials(HTTP_AUTHORIZATION=f'Token {stale}')
    assert client.get(LIST_URL).status_code == 401


# --- Requirement: Never return a password ----------------------------------------------------


@pytest.mark.django_db
def test_a_successful_change_never_returns_a_password(client, administrator, member):
    response = as_user(client, administrator).post(
        admin_url('ada'), {'password': NEW_PASSWORD}, format='json'
    )

    assert NEW_PASSWORD not in response.content.decode()


@pytest.mark.django_db
def test_a_refused_change_never_returns_a_password(client, member):
    response = as_user(client, member).post(
        SELF_URL,
        {'current_password': OLD_PASSWORD, 'new_password': 'a1' + 'x' * 127},
        format='json',
    )

    body = response.content.decode()
    assert OLD_PASSWORD not in body
    assert 'x' * 127 not in body


@pytest.mark.django_db
def test_an_account_named_me_is_still_addressable_by_an_administrator(client, administrator):
    """No username may be unreachable because a fixed route happens to share its spelling.

    Signup could not create this account - its minimum username length is longer - but
    createsuperuser and the shell can, and the requirement says *any* named account.
    """
    awkward = User.objects.create_user(
        username='me', email='me@example.com', password=OLD_PASSWORD
    )

    response = as_user(client, administrator).post(
        admin_url('me'), {'password': NEW_PASSWORD}, format='json'
    )

    assert response.status_code == 200
    awkward.refresh_from_db()
    assert awkward.check_password(NEW_PASSWORD)
