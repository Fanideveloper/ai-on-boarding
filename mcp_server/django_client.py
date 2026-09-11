"""The one place this server talks to the account API.

Two rules live here rather than in the tools, because a rule implemented once cannot be
implemented differently the second time:

* **Field allowlists.** Every response is reduced to the fields the calling tool needs before
  it is returned. A tool cannot widen that, and a field added to the API later does not begin
  reaching the assistant on its own.
* **Refusal wording.** Every non-success is turned into a sentence saying what was refused and
  why. An assistant handed a bare status code retries it or invents a result.

Obtaining the API token also lives here, in one function, so the retry-once rule below exists
once. That function is the seam where a cache or a self-signed token would be substituted if
the round trip ever became worth removing; nothing else would have to change.
"""

from urllib.parse import quote

import requests

# What each call is allowed to return. Anything else the API sends - now or later - is dropped
# before it reaches a tool, and therefore before it reaches the assistant.
ACCOUNT_FIELDS = ('username', 'country', 'date_joined')

REQUEST_TIMEOUT = 10

# A refusal from the API is rendered into a sentence, and part of that sentence is the API's own
# message. Bounded so a malformed or unexpectedly large body cannot flood the assistant's
# context; the API's real messages are one short line.
MAX_DETAIL = 300


class ApiRefusal(Exception):
    """A refusal, already stated in language meant to be read by the calling assistant."""


class DjangoClient:
    """Calls the account API as one particular person.

    Constructed per caller, holding that person's Google access token. Every request is made
    with an API token issued for that person, so the API - not this server - decides what they
    may do.
    """

    def __init__(self, base_url, google_access_token, session=None):
        self._base_url = base_url.rstrip('/')
        self._google_access_token = google_access_token
        self._session = session if session is not None else requests.Session()
        self._api_token = None

    # ---------------------------------------------------------------- the token seam

    def _api_token_for_caller(self, refresh=False):
        """The caller's API token, obtained by presenting their Google access token.

        The single place a token is acquired. v1 asks the API every time a client is built and
        holds it only for that client's lifetime - no cache, no self-signed token. Replacing
        the body of this function is the whole of that change if it is ever made.
        """
        if self._api_token is None or refresh:
            self._api_token = self._exchange_google_token()
        return self._api_token

    def _exchange_google_token(self):
        try:
            response = self._session.post(
                f'{self._base_url}/api/auth/google/',
                json={'access_token': self._google_access_token},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as err:
            raise ApiRefusal('Could not reach the account service.') from err

        if response.status_code == 200:
            # A 200 that is not the API answering - a proxy or a login page at a mistyped
            # base URL - would otherwise raise out of here as something that is not an
            # ApiRefusal, and the framework masks those behind a generic message.
            body = _body(response)
            if body is None or not body.get('token'):
                raise ApiRefusal(
                    'The account service answered the sign-in request with something '
                    'unexpected. Check that the configured address points at the API.'
                )
            return body['token']
        if response.status_code == 403:
            raise ApiRefusal(
                'That Google account cannot sign in here. It needs an account on the account '
                'service using the same email address.'
            )
        if response.status_code == 429:
            raise ApiRefusal('Too many sign-in attempts just now. Try again shortly.')
        raise ApiRefusal('The account service would not accept that Google sign-in.')

    # ---------------------------------------------------------------- transport

    def _send(self, method, path, api_token, **kwargs):
        try:
            return self._session.request(
                method,
                f'{self._base_url}{path}',
                headers={'Authorization': f'Token {api_token}'},
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            )
        except requests.RequestException as err:
            raise ApiRefusal('Could not reach the account service.') from err

    def _request(self, method, path, **kwargs):
        """Send a request, replacing a token the API no longer accepts exactly once.

        A successful password change retires the caller's own tokens, so the token this client
        is holding can stop being accepted part-way through a session - by the very tool call
        that just succeeded. One retry with a fresh token covers that. A second refusal is not
        a stale token and is reported.
        """
        response = self._send(method, path, self._api_token_for_caller(), **kwargs)
        if response.status_code == 401:
            response = self._send(
                method, path, self._api_token_for_caller(refresh=True), **kwargs
            )
        return response

    # ---------------------------------------------------------------- calls

    def list_accounts(self, country=None):
        params = {'country': country} if country else {}
        response = self._request('GET', '/api/users/', params=params)
        if response.status_code != 200:
            raise ApiRefusal(_listing_refusal(response))
        try:
            entries = response.json()
        except ValueError as err:
            raise ApiRefusal(
                'The account service answered with something that was not an account listing. '
                'Check that the configured address points at the API.'
            ) from err
        if not isinstance(entries, list):
            raise ApiRefusal('The account service answered with an unexpected listing shape.')
        return [_only(ACCOUNT_FIELDS, entry) for entry in entries if isinstance(entry, dict)]

    def change_other_password(self, username, new_password):
        # Quoted, not interpolated raw: this segment comes from whatever the assistant was
        # asked to change, and an unencoded '/' or '..' in it would address a different
        # endpoint entirely.
        response = self._request(
            'POST',
            f'/api/users/{quote(username, safe="")}/change-password/',
            json={'password': new_password},
        )
        if response.status_code != 200:
            raise ApiRefusal(_admin_change_refusal(response, username))
        return True

    def change_own_password(self, current_password, new_password):
        response = self._request(
            'POST',
            '/api/me/change-password/',
            json={'current_password': current_password, 'new_password': new_password},
        )
        if response.status_code != 200:
            raise ApiRefusal(_self_change_refusal(response))
        return True


# -------------------------------------------------------------------- refusal wording


def _only(fields, payload):
    """Reduce one API record to the fields a tool is allowed to see."""
    return {name: payload.get(name) for name in fields}


def _body(response):
    """The API's parsed response body, or None if it was not readable JSON.

    Refusals are told apart by which field the API keyed its error on, not by looking for words
    in the message. Wording is presentation and will drift; the key is the contract.
    """
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _detail(response):
    """The API's own explanation, flattened to one bounded line.

    DRF reports an error either as `{"detail": "..."}` or keyed by field, whose values are
    lists. Both are flattened; anything else falls back to the raw body, truncated.
    """
    try:
        body = response.json()
    except ValueError:
        return response.text[:MAX_DETAIL].strip()

    if isinstance(body, dict):
        parts = []
        for value in body.values():
            if isinstance(value, (list, tuple)):
                parts.extend(str(item) for item in value)
            else:
                parts.append(str(value))
        return ' '.join(parts)[:MAX_DETAIL]
    return str(body)[:MAX_DETAIL]


def _listing_refusal(response):
    if response.status_code == 403:
        return 'Listing users requires admin privileges, and this account does not have them.'
    if response.status_code == 401:
        return 'The account service did not accept this session. Sign in again.'
    return f'The account service refused to list users: {_detail(response)}'


def _password_refusal_detail(response):
    """The shared wording for a rejected new password.

    A password refused for its length has to be told the limit, because that is the one refusal
    the caller can act on without guessing - and the API's own message already names it.
    """
    return f'The new password was rejected: {_detail(response)}'


def _admin_change_refusal(response, username):
    if response.status_code == 403:
        return (
            'Changing another account\'s password requires admin privileges, and this account '
            'does not have them. To change your own password instead, give your current '
            'password and no username.'
        )
    if response.status_code == 401:
        return 'The account service did not accept this session. Sign in again.'
    if response.status_code == 404:
        return f'No account named {username!r} exists, so no password was changed.'
    if response.status_code == 400:
        body = _body(response)
        # Keyed on `password` means the new password itself was rejected. Anything else with
        # this status is about the account named - an ambiguous username, for instance - and
        # saying "the new password was rejected" would send the caller to fix the wrong thing.
        if body is not None and 'password' in body:
            return _password_refusal_detail(response)
        return f'The password for {username!r} was not changed: {_detail(response)}'
    return f'The password was not changed: {_detail(response)}'


FORGOTTEN_PASSWORD_ADVICE = (
    'If it has been forgotten, request a reset link by email from the account service instead '
    '- there is no way to change a password without it.'
)


def _self_change_refusal(response):
    if response.status_code == 401:
        return 'The account service did not accept this session. Sign in again.'
    if response.status_code == 400:
        body = _body(response)
        if body is not None:
            # Keyed on the new password: the new one was rejected on its own merits.
            if 'new_password' in body:
                return _password_refusal_detail(response)
            # Keyed on the current password: it was missing or empty, not merely wrong.
            if 'current_password' in body:
                return (
                    'No current password was given, so the password was not changed. '
                    + FORGOTTEN_PASSWORD_ADVICE
                )
            # The endpoint's only other refusal at this status is a current password that did
            # not match. Recognised by the shape of the body rather than by its wording, so a
            # reworded message cannot silently reclassify it as a rejected new password.
            if 'detail' in body:
                return (
                    'The current password given was not correct, so the password was not '
                    'changed. ' + FORGOTTEN_PASSWORD_ADVICE
                )
        # Not something this endpoint produces - a proxy or a misconfigured host, most likely.
        # Guessing "your current password was wrong" here would send someone to reset a
        # password that was never the problem.
        return f'The password was not changed: {_detail(response)}'
    return f'The password was not changed: {_detail(response)}'
