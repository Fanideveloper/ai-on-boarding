"""What each tool does, independent of the MCP framework.

Deliberately importing nothing from fastmcp. The framework's job is authenticating the caller
and publishing these; what a tool actually does is decided here, and can be exercised against a
stubbed API without standing up an OAuth flow.

Every refusal leaves here as an ApiRefusal carrying a sentence meant to be read by the calling
assistant. server.py turns that into the framework's own error type.
"""

from django_client import ApiRefusal


def list_accounts(client):
    """Every account, as the API returns them."""
    return client.list_accounts()


def list_accounts_from_country(client, country):
    """Accounts recording a given country, matched without regard to case."""
    if not country or not country.strip():
        raise ApiRefusal('Name the country to list accounts from.')
    return client.list_accounts(country=country.strip())


def change_password(client, new_password, username=None, current_password=None):
    """Change a password, either the caller's own or - for an administrator - another account's.

    Exactly one of the two decides: a `current_password` means the caller's own account, a
    `username` means somebody else's. Both together are refused rather than guessed at, because
    either guess strands somebody - preferring the username leaves a non-administrator who
    named themselves with a privileges refusal, and preferring the current password silently
    changes an administrator's own password when they meant to change the account they named.
    Asking is cheap; changing the wrong account's password is not.

    Returns a sentence describing what happened. It says a password was changed only when the
    API confirmed it did - an assistant reporting a refusal as a success is the failure this
    guards against.
    """
    if not new_password:
        raise ApiRefusal('Give the new password to set.')

    if username and current_password:
        raise ApiRefusal(
            'Give either a username or a current password, not both, so it is unambiguous '
            "whose password to change. Name a username to change that account's password, "
            'which needs admin privileges; give your current password and no username to '
            'change your own.'
        )

    if current_password:
        client.change_own_password(current_password, new_password)
        return 'Your own password has been changed. Any existing sessions have been signed out.'

    if not username:
        raise ApiRefusal(
            'Changing your own password requires your current password. To change a different '
            "account's password instead, name it - that needs admin privileges. If your "
            'current password has been forgotten, request a reset link by email from the '
            'account service.'
        )

    client.change_other_password(username, new_password)
    return (
        f'The password for {username!r} has been changed. '
        'That account has been signed out of any existing sessions.'
    )
