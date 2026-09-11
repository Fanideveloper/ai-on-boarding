"""Tests for how the server is wired, written from
openspec/changes/add-mcp-user-management/specs/mcp-server.

These cover the two pieces nothing else touches: the seam that decides whose credential a tool
acts with, and the scopes the server asks Google for. Both are invisible from the tool tests -
replacing the caller's identity with a shared credential, or asking Google for the wrong
scopes, leaves every other test passing while the feature is broken or unsafe.
"""

import asyncio

import pytest
from fastmcp.exceptions import ToolError

from django_client import DjangoClient
from server import client_for_access_token, create_server

API_BASE_URL = 'http://accounts.test'


class StubAccessToken:
    """What the provider hands a tool: the caller's own upstream Google access token."""

    def __init__(self, token):
        self.token = token


# --- Requirement: Act with the calling person's own privileges -------------------------------


def test_the_client_carries_the_callers_own_token_not_a_shared_one():
    """The API must see the person, not this server.

    If this ever became a credential of the server's own, the API could not tell an
    administrator from anyone else and the admin-versus-self distinction would collapse -
    silently, because every tool would go on working.
    """
    caller = StubAccessToken('this-callers-google-access-token')

    client = client_for_access_token(API_BASE_URL, caller)

    assert isinstance(client, DjangoClient)
    assert client._google_access_token == 'this-callers-google-access-token'


def test_two_callers_do_not_share_a_credential():
    first = client_for_access_token(API_BASE_URL, StubAccessToken('first-callers-token'))
    second = client_for_access_token(API_BASE_URL, StubAccessToken('second-callers-token'))

    assert first._google_access_token != second._google_access_token


def test_a_request_with_no_identity_is_refused_rather_than_acted_on():
    with pytest.raises(ToolError) as error:
        client_for_access_token(API_BASE_URL, None)

    assert 'no signed-in identity' in str(error.value)


# --- Requirement: Sign in with a verified Google access token --------------------------------


def test_the_server_asks_google_for_an_address_not_just_an_identifier():
    """`openid` alone returns an opaque subject and no address.

    The account API signs someone in by matching a verified email address, so a server that
    asked only for `openid` would have every one of its callers refused - and the refusal is
    the same generic one every other token-side failure produces, so nothing would say why.
    """
    mcp = create_server(API_BASE_URL, 'cid.apps.googleusercontent.com', 'secret',
                        'http://localhost:8000')

    scopes = mcp.auth.required_scopes
    assert any('email' in scope for scope in scopes), scopes


# --- Requirement: Expose a tool that lists accounts / from a country / changes a password ----


def test_the_server_publishes_exactly_the_three_tools():
    # asyncio.run rather than an async test, so the suite needs no extra plugin.
    mcp = create_server(API_BASE_URL, 'cid.apps.googleusercontent.com', 'secret',
                        'http://localhost:8000')

    published = {tool.name for tool in asyncio.run(mcp._list_tools())}

    assert published == {'list_users', 'list_users_by_country', 'change_password'}
