"""Tests for what each tool does, written from
openspec/changes/add-mcp-user-management/specs/mcp-server.

The API is stubbed through a fake client, so these say what a tool asks for and what it reports
back - not how the HTTP call is made, which test_django_client.py covers.
"""

import pytest
from fastmcp.exceptions import ToolError

import tools
from django_client import ApiRefusal
from server import run_action

ACCOUNTS = [
    {'username': 'ada', 'country': 'pakistan', 'date_joined': '2026-01-01T00:00:00Z'},
    {'username': 'alan', 'country': 'united kingdom', 'date_joined': '2026-01-02T00:00:00Z'},
]


class StubClient:
    """Stands in for the API client, recording what a tool asked it to do."""

    def __init__(self, accounts=None, refusal=None):
        self._accounts = ACCOUNTS if accounts is None else accounts
        self._refusal = refusal
        self.calls = []

    def list_accounts(self, country=None, username=None):
        self.calls.append(('list_accounts', country, username))
        if self._refusal:
            raise self._refusal
        if country:
            return [a for a in self._accounts if a['country'].lower() == country.lower()]
        return self._accounts

    def change_own_password(self, current_password, new_password):
        self.calls.append(('change_own_password', current_password, new_password))
        if self._refusal:
            raise self._refusal
        return True

    def change_other_password(self, username, new_password):
        self.calls.append(('change_other_password', username, new_password))
        if self._refusal:
            raise self._refusal
        return True


# --- Requirement: Expose a tool that lists accounts ------------------------------------------


def test_the_listing_tool_returns_every_account():
    client = StubClient()

    assert tools.list_accounts(client) == ACCOUNTS
    assert client.calls == [('list_accounts', None, None)]


# --- Requirement: Expose a tool that lists accounts from a country ---------------------------


def test_the_country_tool_returns_only_accounts_from_that_country():
    client = StubClient()

    result = tools.list_accounts_from_country(client, 'pakistan')

    assert [a['username'] for a in result] == ['ada']


def test_a_country_named_in_a_different_case_returns_the_same_accounts():
    client = StubClient()

    result = tools.list_accounts_from_country(client, 'PaKiStAn')

    assert [a['username'] for a in result] == ['ada']


def test_an_empty_country_is_refused_before_the_api_is_called():
    client = StubClient()

    with pytest.raises(ApiRefusal):
        tools.list_accounts_from_country(client, '   ')

    assert client.calls == []


# --- Requirement: Expose a tool that changes a password --------------------------------------


def test_omitting_a_username_changes_the_callers_own_password():
    client = StubClient()

    message = tools.change_password(client, 'babbage22', current_password='lovelace1')

    assert client.calls == [('change_own_password', 'lovelace1', 'babbage22')]
    assert 'Your own password has been changed' in message


def test_naming_an_account_changes_that_accounts_password():
    client = StubClient()

    message = tools.change_password(client, 'babbage22', username='ada')

    assert client.calls == [('change_other_password', 'ada', 'babbage22')]
    assert "'ada'" in message


def test_changing_your_own_password_without_the_current_one_is_refused_locally():
    """Refused before the API is called, and the refusal names the way out.

    The account service would refuse it too, but a round trip to be told what this server
    already knows helps nobody.
    """
    client = StubClient()

    with pytest.raises(ApiRefusal) as refusal:
        tools.change_password(client, 'babbage22')

    assert client.calls == []
    assert 'reset link by email' in str(refusal.value)


# --- Requirement: Report the account system's actual verdict ---------------------------------


def test_a_refused_password_change_is_never_reported_as_a_success():
    """The failure this guards against is an assistant saying 'Done!' after a refusal."""
    client = StubClient(refusal=ApiRefusal('The new password was rejected: too long.'))

    with pytest.raises(ApiRefusal):
        tools.change_password(client, 'x' * 200, username='ada')


def test_a_refusal_reaches_the_assistant_as_the_frameworks_own_error():
    """Not cosmetic: FastMCP masks an unexpected exception behind a generic message, so a
    refusal that escaped untranslated would lose the wording entirely."""
    client = StubClient(refusal=ApiRefusal('Listing users requires admin privileges.'))

    with pytest.raises(ToolError) as error:
        run_action(client, tools.list_accounts)

    assert 'admin privileges' in str(error.value)


def test_a_successful_action_passes_through_run_action_unchanged():
    client = StubClient()

    assert run_action(client, tools.list_accounts) == ACCOUNTS


def test_an_empty_username_is_treated_as_the_callers_own_account():
    """An assistant filling in a blank rather than omitting the field meant 'mine'."""
    client = StubClient()

    tools.change_password(client, 'babbage22', username='', current_password='lovelace1')

    assert client.calls == [('change_own_password', 'lovelace1', 'babbage22')]


def test_giving_both_a_username_and_a_current_password_is_refused_not_guessed():
    """Either guess strands somebody, and one of them changes the wrong account's password.

    Preferring the username leaves a non-administrator who named themselves with a privileges
    refusal. Preferring the current password silently changes an administrator's own password
    when they meant the account they named. Nothing is sent to the API either way.
    """
    client = StubClient()

    with pytest.raises(ApiRefusal) as refusal:
        tools.change_password(
            client, 'babbage22', username='ada', current_password='lovelace1'
        )

    assert client.calls == []
    message = str(refusal.value)
    assert 'not both' in message
    assert 'admin privileges' in message
