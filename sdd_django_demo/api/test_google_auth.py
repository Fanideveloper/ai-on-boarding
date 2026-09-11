"""Tests for Google signin, written from openspec/changes/add-mcp-user-management/specs/user-signin.

Google is never actually called: `verify_access_token` is the only thing that reaches it, and
what these tests care about is what this project does with the answer. The stub stands in for
tokeninfo's response, including its habit of reporting `email_verified` as the string 'true'.
"""

import pytest
import requests
from django.contrib.auth.models import User
from django.core.cache import cache

from api import google_auth
from embargo.models import AccountCountry, BlockedCountry

URL = '/api/auth/google/'
CLIENT_ID = 'client-one.apps.googleusercontent.com'
OTHER_CLIENT_ID = 'client-two.apps.googleusercontent.com'
ADDRESS = 'ada@example.com'


class FakeTokeninfoResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """The signin cap is keyed on the caller, and every test here is the same caller.

    Without this, a test would be throttled by the requests its predecessors made and would
    fail for a reason that has nothing to do with what it asserts.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def google(monkeypatch, settings):
    """Stub Google, routing by endpoint, and record every call made to it.

    Two endpoints answer different questions: tokeninfo describes the token, userinfo describes
    the account. `hd` lives only on the account, so the hosted-domain tests supply a `profile`
    rather than smuggling `hd` into the token description - which is what would let a broken
    implementation pass.
    """
    settings.GOOGLE_OAUTH_CLIENT_IDS = [CLIENT_ID]
    settings.GOOGLE_ALLOWED_HD = ''
    calls = []

    def install(payload, status_code=200, unreachable=False, profile=None):
        def fake_get(url, **kwargs):
            calls.append(url)
            if unreachable:
                raise requests.ConnectionError('google is down')
            if url == google_auth.USERINFO_URL:
                return FakeTokeninfoResponse(profile if profile is not None else {}, 200)
            return FakeTokeninfoResponse(payload, status_code)

        monkeypatch.setattr(google_auth.requests, 'get', fake_get)

    install.calls = calls
    return install


def claims(**overrides):
    return {'aud': CLIENT_ID, 'email_verified': 'true', 'email': ADDRESS, **overrides}


def signin(client, access_token='an-access-token'):
    return client.post(URL, {'access_token': access_token}, format='json')


def account(username='ada', email=ADDRESS):
    return User.objects.create_user(username=username, email=email, password='lovelace1')


# --- Requirement: Sign in with a verified Google access token -------------------------------


@pytest.mark.django_db
def test_a_verified_token_for_a_matching_account_signs_in(client, google):
    account()
    google(claims())

    response = signin(client)

    assert response.status_code == 200
    assert response.data['token']


@pytest.mark.django_db
def test_the_same_account_may_sign_in_repeatedly(client, google):
    account()
    google(claims())

    first = signin(client)
    second = signin(client)

    assert first.status_code == second.status_code == 200
    assert first.data['token'] and second.data['token']


# --- Requirement: Accept only a token issued for this application ---------------------------


@pytest.mark.django_db
def test_a_token_issued_for_another_application_is_refused(client, google):
    account()
    google(claims(aud='someone-elses-client.apps.googleusercontent.com'))

    response = signin(client)

    assert response.status_code == 401
    assert 'token' not in response.data


@pytest.mark.django_db
def test_a_second_configured_client_id_is_accepted(client, google, settings):
    account()
    settings.GOOGLE_OAUTH_CLIENT_IDS = [CLIENT_ID, OTHER_CLIENT_ID]
    google(claims(aud=OTHER_CLIENT_ID))

    response = signin(client)

    assert response.status_code == 200


# --- Requirement: Require a verified email address ------------------------------------------


@pytest.mark.django_db
def test_an_unverified_address_is_refused(client, google):
    account()
    google(claims(email_verified='false'))

    response = signin(client)

    assert response.status_code == 401
    assert 'token' not in response.data


# --- Requirement: Refuse an absent or ambiguous matching account ----------------------------


@pytest.mark.django_db
def test_a_token_matching_no_account_is_refused(client, google):
    google(claims())

    response = signin(client)

    assert response.status_code == 403
    assert 'token' not in response.data


@pytest.mark.django_db
def test_a_token_matching_more_than_one_account_is_refused(client, google):
    account(username='ada')
    account(username='ada2', email=ADDRESS.upper())
    google(claims())

    response = signin(client)

    assert response.status_code == 403
    assert 'token' not in response.data


# --- Requirement: Refuse an embargoed account -----------------------------------------------


@pytest.mark.django_db
def test_an_embargoed_account_is_refused(client, google):
    user = account()
    blocked = BlockedCountry.objects.first()
    assert blocked is not None, 'expected a blocked country to exist'
    AccountCountry.objects.create(user=user, country=blocked.country)
    google(claims())

    response = signin(client)

    assert response.status_code == 403
    assert 'token' not in response.data


# --- Requirement: Restrict Google sign-in to a configured hosted domain ----------------------


@pytest.mark.django_db
def test_a_matching_hosted_domain_signs_in(client, google, settings):
    account()
    settings.GOOGLE_ALLOWED_HD = 'example.com'
    google(claims(), profile={'hd': 'example.com'})

    assert signin(client).status_code == 200


@pytest.mark.django_db
def test_a_hosted_domain_differing_only_in_case_signs_in(client, google, settings):
    account()
    settings.GOOGLE_ALLOWED_HD = 'example.com'
    google(claims(), profile={'hd': 'ExAmPlE.CoM'})

    assert signin(client).status_code == 200


@pytest.mark.django_db
def test_a_non_matching_hosted_domain_is_refused(client, google, settings):
    account()
    settings.GOOGLE_ALLOWED_HD = 'example.com'
    google(claims(), profile={'hd': 'elsewhere.com'})

    response = signin(client)

    assert response.status_code == 401
    assert 'token' not in response.data


@pytest.mark.django_db
def test_an_absent_hosted_domain_is_refused_when_one_is_required(client, google, settings):
    """A personal account carries no `hd` at all, and must not satisfy a domain restriction.

    The address's own domain is not a substitute: anyone can hold a Gmail account whose
    address ends in the right characters.
    """
    account()
    settings.GOOGLE_ALLOWED_HD = 'example.com'
    google(claims())

    response = signin(client)

    assert response.status_code == 401
    assert 'token' not in response.data


@pytest.mark.django_db
def test_an_absent_hosted_domain_is_fine_when_none_is_required(client, google, settings):
    account()
    settings.GOOGLE_ALLOWED_HD = ''
    google(claims())

    assert signin(client).status_code == 200


# --- Requirement: Reject every Google-side refusal identically ------------------------------


@pytest.mark.django_db
def test_two_different_token_side_refusals_are_indistinguishable(client, google):
    account()

    google(claims(aud='someone-else.apps.googleusercontent.com'))
    wrong_audience = signin(client)
    google(claims(email_verified='false'))
    unverified_address = signin(client)
    google({}, status_code=400)
    google_said_no = signin(client)
    google(None, unreachable=True)
    google_unreachable = signin(client)

    responses = [wrong_audience, unverified_address, google_said_no, google_unreachable]
    assert {r.status_code for r in responses} == {401}
    assert len({r.content for r in responses}) == 1


@pytest.mark.django_db
def test_two_different_account_side_refusals_are_indistinguishable(client, google):
    google(claims())
    no_account = signin(client)

    account(username='ada')
    account(username='ada2', email=ADDRESS.upper())
    ambiguous = signin(client)

    assert no_account.status_code == ambiguous.status_code == 403
    assert no_account.content == ambiguous.content


# --- Requirement: Never return a token in a Google sign-in rejection ------------------------


@pytest.mark.django_db
def test_no_rejection_carries_a_token_or_echoes_the_submitted_one(client, google):
    submitted = 'the-callers-google-access-token'
    account()

    google(claims(aud='someone-else.apps.googleusercontent.com'))
    token_side = signin(client, submitted)
    google(claims(email='nobody@example.com'))
    account_side = signin(client, submitted)

    for response in (token_side, account_side):
        body = response.content.decode()
        assert 'token' not in response.data
        assert submitted not in body


# --- Requirement: Limit how often Google sign-in may be attempted ---------------------------


@pytest.mark.django_db
def test_attempts_beyond_the_cap_are_refused(client, google):
    account()
    google(claims())

    statuses = [signin(client).status_code for _ in range(25)]

    assert 429 in statuses
    assert statuses[0] == 200


@pytest.mark.django_db
def test_a_refused_attempt_never_reaches_google(client, google):
    """The limit exists to bound outbound traffic, so it has to refuse before making any.

    Asserted by counting calls to the stub rather than by reading the response, because a
    refusal that still called Google would look identical from the outside.
    """
    account()
    google(claims())

    while signin(client).status_code != 429:
        pass
    calls_before = len(google.calls)
    assert signin(client).status_code == 429

    assert len(google.calls) == calls_before


@pytest.mark.django_db
def test_the_cap_cannot_be_walked_through_by_varying_a_forwarded_header(client, google):
    """The limit keys on the caller, and a caller must not be able to choose their own key.

    X-Forwarded-For is written by whoever is calling. With DRF's default proxy setting it is
    trusted outright, so varying it gives every request a fresh bucket and the cap stops
    existing. Asserted by counting calls to Google, which is the traffic the cap protects.
    """
    account()
    google(claims())

    for attempt in range(40):
        client.post(
            URL,
            {'access_token': 'an-access-token'},
            format='json',
            HTTP_X_FORWARDED_FOR=f'203.0.113.{attempt}',
        )

    assert len(google.calls) <= 20, (
        f'{len(google.calls)} attempts reached Google against a 20/min cap'
    )


@pytest.mark.django_db
def test_the_ordinary_path_asks_google_exactly_once(client, google):
    """With no domain restriction configured, the account profile is never fetched.

    The hosted-domain check is the only thing that needs it, so paying for it on every signin
    would be a round trip bought for nothing.
    """
    account()
    google(claims())

    assert signin(client).status_code == 200

    assert google.calls == [google_auth.TOKENINFO_URL]


@pytest.mark.django_db
def test_a_hosted_domain_restriction_reads_the_account_not_the_token(client, google, settings):
    """`hd` describes the account and never appears in a token description.

    A token description carrying `hd` must therefore not satisfy the restriction - if it did,
    the check would be reading a field Google does not put there, and the restriction would
    refuse every real Workspace account instead.
    """
    account()
    settings.GOOGLE_ALLOWED_HD = 'example.com'
    google(claims(hd='example.com'), profile={})

    response = signin(client)

    assert response.status_code == 401
    assert google_auth.USERINFO_URL in google.calls
