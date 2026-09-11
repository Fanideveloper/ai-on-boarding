"""Tests for the API client, written from
openspec/changes/add-mcp-user-management/specs/mcp-server.

The API is stubbed throughout. What these protect is the boundary this server puts between the
API and the assistant: which fields survive it, what a refusal is turned into, and how a token
the API has stopped accepting is replaced.
"""

import pytest
import requests

from django_client import ACCOUNT_FIELDS, ApiRefusal, DjangoClient

BASE_URL = 'http://accounts.test'
GOOGLE_ACCESS_TOKEN = 'the-callers-google-access-token'
API_TOKEN = 'the-callers-api-token'


class StubResponse:
    def __init__(self, status_code, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError('not json')
        return self._payload


class StubSession:
    """Answers each call with the next queued response, and records what it was asked."""

    def __init__(self, *responses):
        self.queue = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        return self._answer('POST', url, kwargs)

    def request(self, method, url, **kwargs):
        return self._answer(method, url, kwargs)

    def _answer(self, method, url, kwargs):
        self.calls.append((method, url, kwargs))
        if not self.queue:
            raise AssertionError(f'unexpected extra request: {method} {url}')
        answer = self.queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def signed_in():
    return StubResponse(200, {'token': API_TOKEN})


def build(*responses):
    session = StubSession(*responses)
    return DjangoClient(BASE_URL, GOOGLE_ACCESS_TOKEN, session=session), session


# --- Requirement: Act with the calling person's own privileges -------------------------------


def test_the_callers_own_google_token_buys_the_api_token_used_for_every_request():
    client, session = build(signed_in(), StubResponse(200, []))

    client.list_accounts()

    method, url, kwargs = session.calls[0]
    assert (method, url) == ('POST', f'{BASE_URL}/api/auth/google/')
    assert kwargs['json'] == {'access_token': GOOGLE_ACCESS_TOKEN}
    assert session.calls[1][2]['headers']['Authorization'] == f'Token {API_TOKEN}'


def test_a_google_account_with_no_account_here_is_refused():
    client, _ = build(StubResponse(403, {'detail': 'no'}))

    with pytest.raises(ApiRefusal) as refusal:
        client.list_accounts()

    assert 'cannot sign in here' in str(refusal.value)


def test_an_unreachable_account_service_is_reported_not_raised_raw():
    client, _ = build(requests.ConnectionError('down'))

    with pytest.raises(ApiRefusal) as refusal:
        client.list_accounts()

    assert 'Could not reach' in str(refusal.value)


# --- Requirement: Disclose only the fields a tool needs --------------------------------------


def test_no_field_beyond_the_allowlist_survives_the_client():
    """The allowlist is the seam, so this asserts against a response deliberately carrying
    exactly the things that must never reach the assistant."""
    leaking = {
        'username': 'ada',
        'country': 'pakistan',
        'date_joined': '2026-01-01T00:00:00Z',
        'email': 'ada@example.com',
        'id': 7,
        'is_staff': True,
        'password': 'pbkdf2_sha256$...',
    }
    client, _ = build(signed_in(), StubResponse(200, [leaking]))

    entry = client.list_accounts()[0]

    assert set(entry) == set(ACCOUNT_FIELDS)
    for forbidden in ('email', 'id', 'is_staff', 'password'):
        assert forbidden not in entry


def test_a_field_the_api_adds_later_does_not_begin_reaching_the_assistant():
    client, _ = build(
        signed_in(),
        StubResponse(200, [{'username': 'ada', 'country': None, 'date_joined': 'x',
                            'something_invented_later': 'surprise'}]),
    )

    assert 'something_invented_later' not in client.list_accounts()[0]


def test_an_allowed_field_the_api_omits_comes_back_empty_rather_than_missing():
    client, _ = build(signed_in(), StubResponse(200, [{'username': 'ada'}]))

    assert client.list_accounts()[0] == {
        'username': 'ada', 'country': None, 'date_joined': None
    }


# --- Requirement: Obtain a fresh authentication token once before failing --------------------


def test_a_token_the_api_stopped_accepting_is_replaced_and_the_request_retried():
    """A successful password change retires the caller's own tokens, so this is the ordinary
    path immediately after one - not an exotic failure."""
    client, session = build(
        signed_in(), StubResponse(401), signed_in(), StubResponse(200, [])
    )

    assert client.list_accounts() == []

    assert [method for method, _, _ in session.calls] == ['POST', 'GET', 'POST', 'GET']


def test_a_second_refusal_is_reported_rather_than_retried_again():
    client, session = build(
        signed_in(), StubResponse(401), signed_in(), StubResponse(401)
    )

    with pytest.raises(ApiRefusal):
        client.list_accounts()

    assert len(session.calls) == 4


# --- Requirement: State a refusal in plain language ------------------------------------------


def test_a_listing_refused_to_a_non_administrator_says_so():
    client, _ = build(signed_in(), StubResponse(403, {'detail': 'Forbidden'}))

    with pytest.raises(ApiRefusal) as refusal:
        client.list_accounts()

    assert 'admin privileges' in str(refusal.value)


def test_a_password_refused_for_its_length_names_the_maximum():
    client, _ = build(
        signed_in(),
        StubResponse(400, {'password': ['Must be at most 128 characters.']}),
    )

    with pytest.raises(ApiRefusal) as refusal:
        client.change_other_password('ada', 'x' * 200)

    assert 'at most 128' in str(refusal.value)


def test_an_unknown_account_is_named_in_the_refusal():
    client, _ = build(
        signed_in(), StubResponse(404, {'detail': 'No account with that username.'})
    )

    with pytest.raises(ApiRefusal) as refusal:
        client.change_other_password('nobody', 'babbage22')

    assert 'nobody' in str(refusal.value)


def test_an_unreadable_refusal_body_does_not_break_the_wording():
    client, _ = build(signed_in(), StubResponse(500, None, text='<html>oh dear</html>'))

    with pytest.raises(ApiRefusal) as refusal:
        client.list_accounts()

    assert 'refused to list users' in str(refusal.value)


def test_a_refusal_body_cannot_flood_the_assistant():
    client, _ = build(signed_in(), StubResponse(500, None, text='x' * 10_000))

    with pytest.raises(ApiRefusal) as refusal:
        client.list_accounts()

    assert len(str(refusal.value)) < 500


# --- Requirement: Point a caller who lacks their current password at the reset flow ----------


def test_a_wrong_current_password_points_at_the_email_reset_flow():
    client, _ = build(
        signed_in(), StubResponse(400, {'detail': 'Current password is incorrect.'})
    )

    with pytest.raises(ApiRefusal) as refusal:
        client.change_own_password('not-it', 'babbage22')

    message = str(refusal.value)
    assert 'not correct' in message
    assert 'reset link by email' in message


# --- Requirement: Expose a tool that lists accounts from a country ---------------------------


def test_a_country_is_passed_through_as_a_filter():
    client, session = build(signed_in(), StubResponse(200, []))

    client.list_accounts(country='Pakistan')

    assert session.calls[1][2]['params'] == {'country': 'Pakistan'}


def test_a_username_is_encoded_before_it_reaches_the_url():
    """The name comes from the assistant, so it cannot be trusted as a path segment."""
    client, session = build(signed_in(), StubResponse(200, {'detail': 'Password changed.'}))

    client.change_other_password('../../admin', 'babbage22')

    _, url, _ = session.calls[1]
    assert '../..' not in url
    assert url.endswith('/api/users/..%2F..%2Fadmin/change-password/')


def test_an_ambiguous_username_is_not_reported_as_a_rejected_password():
    """Both refusals arrive as 400; only one of them is about the password.

    Telling a caller their new password was rejected, when the real problem was the account
    they named, sends them to fix something that was never wrong.
    """
    client, _ = build(
        signed_in(),
        StubResponse(400, {'detail': 'More than one account matches that username.'}),
    )

    with pytest.raises(ApiRefusal) as refusal:
        client.change_other_password('ada', 'babbage22')

    message = str(refusal.value)
    assert 'More than one account matches' in message
    assert 'new password was rejected' not in message


def test_a_missing_current_password_is_not_reported_as_a_rejected_new_password():
    client, _ = build(
        signed_in(),
        StubResponse(400, {'current_password': ['This field may not be blank.']}),
    )

    with pytest.raises(ApiRefusal) as refusal:
        client.change_own_password('', 'babbage22')

    message = str(refusal.value)
    assert 'No current password was given' in message
    assert 'reset link by email' in message


def test_a_rejected_new_password_is_classified_by_its_field_not_its_wording():
    client, _ = build(
        signed_in(),
        StubResponse(400, {'new_password': ['Must be at most 128 characters.']}),
    )

    with pytest.raises(ApiRefusal) as refusal:
        client.change_own_password('lovelace1', 'x' * 200)

    assert 'at most 128' in str(refusal.value)


def test_a_reworded_wrong_current_password_is_still_recognised():
    """Classification must not depend on the API's exact phrasing."""
    client, _ = build(
        signed_in(), StubResponse(400, {'detail': 'That is not the right password.'})
    )

    with pytest.raises(ApiRefusal) as refusal:
        client.change_own_password('nope', 'babbage22')

    assert 'was not correct' in str(refusal.value)


def test_an_unparseable_400_is_not_reported_as_a_wrong_current_password():
    """A proxy or misconfigured host can answer 400 with something that is not the API.

    Guessing "your current password was wrong" there sends someone off to reset a password
    that was never the problem.
    """
    client, _ = build(signed_in(), StubResponse(400, None, text='<html>Bad Request</html>'))

    with pytest.raises(ApiRefusal) as refusal:
        client.change_own_password('lovelace1', 'babbage22')

    message = str(refusal.value)
    assert 'not correct' not in message
    assert 'was not changed' in message


@pytest.mark.parametrize('responses', [
    # A mistyped base URL answering 200 with someone else's login page.
    (StubResponse(200, None, text='<html>some other service</html>'),),
    # The API's own shape changing under us.
    (signed_in(), StubResponse(200, {'results': [], 'count': 0})),
])
def test_an_unexpected_200_is_reported_rather_than_escaping(responses):
    """Left unguarded these raise ValueError, which is not an ApiRefusal, so the framework
    masks them behind a generic message - the exact outcome this module exists to prevent."""
    client, _ = build(*responses)

    with pytest.raises(ApiRefusal):
        client.list_accounts()
