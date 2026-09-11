"""The MCP server: authenticate the caller with Google, then act as them against the account API.

Authentication is FastMCP's GoogleProvider with its default behaviour: its credential check is
not overridden, and nothing here caches the account API's token between tool calls. Those are
performance choices, not correctness ones - see the change's design.md, where they are recorded
as non-goals.

What "default behaviour" includes is worth stating plainly, because it is not nothing. The
proxy underneath GoogleProvider mints FastMCP JWTs of its own, signing them with a key derived
from the Google client secret, and persists each caller's upstream Google tokens to an
encrypted on-disk store. Because GoogleProvider requests offline access, those include Google
refresh tokens. None of that is this module's doing and none of it is configured away here -
but a deployment owns that directory, and should treat it as it would any other credential
store.

What that default gives us is exactly what the account API needs: the provider validates the
caller's Google token on each request and hands the tool an access token whose value is the
caller's own upstream Google access token. That is what gets presented to the API, so the API
issues a token for the calling person and decides for itself what they may do.
"""

import os

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token

import tools
from django_client import ApiRefusal, DjangoClient


def run_action(client, action, *args, **kwargs):
    """Run a tool action, restating a refusal as the framework's own error.

    Load-bearing rather than tidy: FastMCP masks an unexpected exception behind a generic
    message, so an ApiRefusal allowed to escape would reach the assistant stripped of the
    explanation the client layer went to the trouble of composing - and an assistant handed an
    unexplained failure retries it or invents a result.
    """
    try:
        return action(client, *args, **kwargs)
    except ApiRefusal as refusal:
        raise ToolError(str(refusal)) from refusal


def client_for_access_token(api_base_url, access_token):
    """A client that acts as whoever is calling.

    `access_token.token` is the caller's *own* Google access token - the provider resolves it
    from whatever credential the client presented. Presenting that to the account API is what
    makes the API issue a token for this person rather than for this server, and it is the
    whole reason an administrator can be told apart from anyone else. A shared credential here
    would collapse that distinction while leaving every tool apparently working, so this is
    kept at module level with tests of its own rather than buried in a closure.
    """
    if access_token is None:
        raise ToolError('This request carried no signed-in identity.')
    return DjangoClient(api_base_url, access_token.token)


def create_server(api_base_url, google_client_id, google_client_secret, mcp_base_url):
    """Build the server. Separated from module import so it can be built with test values."""
    mcp = FastMCP(
        'account-management',
        auth=GoogleProvider(
            client_id=google_client_id,
            client_secret=google_client_secret,
            base_url=mcp_base_url,
            # Asked for explicitly. The provider's default is 'openid' alone, which grants
            # only an opaque subject identifier: Google then returns no address at all, and
            # the account API - which signs someone in by matching a verified address, and
            # optionally by their Workspace domain - would refuse every caller. Neither
            # failure is visible from here, because every token-side refusal shares one
            # response body by design.
            required_scopes=['openid', 'email'],
        ),
    )

    def client_for_caller():
        return client_for_access_token(api_base_url, get_access_token())

    def run(action, *args, **kwargs):
        return run_action(client_for_caller(), action, *args, **kwargs)

    @mcp.tool
    def list_users() -> list[dict]:
        """List the accounts on the account service.

        Returns each account's username, the country recorded when it signed up, and the date
        it was created. Requires administrator privileges. Accounts created outside the signup
        flow have no country and report it as empty.
        """
        return run(tools.list_accounts)

    @mcp.tool
    def list_users_by_country(country: str) -> list[dict]:
        """List the accounts that signed up from one country.

        The country is matched without regard to case, so "pakistan" and "Pakistan" behave the
        same. Requires administrator privileges.
        """
        return run(tools.list_accounts_from_country, country)

    @mcp.tool
    def change_password(
        new_password: str,
        username: str | None = None,
        current_password: str | None = None,
    ) -> str:
        """Change an account's password.

        Omit `username` to change your own password; that requires `current_password`. Give a
        `username` to change another account's password, which requires administrator
        privileges and no current password.

        A successful change signs that account out of its existing sessions. The password must
        satisfy the account service's rules, including its maximum length; if it does not, the
        refusal says so and nothing is changed.
        """
        return run(
            tools.change_password,
            new_password,
            username=username,
            current_password=current_password,
        )

    return mcp


def create_server_from_environment():
    missing = [
        name
        for name in ('DJANGO_API_BASE_URL', 'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET',
                     'MCP_BASE_URL')
        if not os.environ.get(name)
    ]
    if missing:
        raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")
    return create_server(
        api_base_url=os.environ['DJANGO_API_BASE_URL'],
        google_client_id=os.environ['GOOGLE_CLIENT_ID'],
        google_client_secret=os.environ['GOOGLE_CLIENT_SECRET'],
        mcp_base_url=os.environ['MCP_BASE_URL'],
    )


if __name__ == '__main__':
    create_server_from_environment().run(transport='http')
