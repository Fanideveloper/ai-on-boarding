"""Decide whether a Google access token is one this project will sign someone in with.

Verification, not exchange: the caller completes the Google login themselves and sends the
resulting access token here. This project never redeems an authorization code and so never
holds a Google client secret - see the change's design.md.

Two Google endpoints are involved, for different things:

* **tokeninfo** describes the token - who it was minted for, and which verified address it
  belongs to. That is everything the ordinary path needs, and it is the only call made.
* **userinfo** describes the account. It is asked only when a hosted-domain restriction is
  configured, because the hosted-domain attestation is a property of the account and does not
  appear in a token description at all.
"""

import logging

import requests
from django.conf import settings

TOKENINFO_URL = 'https://oauth2.googleapis.com/tokeninfo'
USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'

# Bounded on purpose. Google signin is unauthenticated, and a request left to hang would hold a
# worker for as long as Google took to answer.
GOOGLE_TIMEOUT = 5

logger = logging.getLogger(__name__)


class GoogleTokenError(Exception):
    """A token this project will not sign anyone in with.

    One exception type for every token-side refusal - unrecognised, wrong audience, unverified
    address, wrong hosted domain, Google unreachable. The caller answers all of them with one
    response, so distinguishing them here would only invite a caller to stop doing that.
    """


def verify_access_token(access_token):
    """Return Google's claims for an access token, or raise GoogleTokenError."""
    claims = _ask_google(TOKENINFO_URL, params={'access_token': access_token})

    # The audience is the client id the token was minted for. Without this check, any other
    # Google application could hand us one of its own users' tokens and be believed. An empty
    # allowlist therefore accepts nothing rather than everything.
    if claims.get('aud') not in settings.GOOGLE_OAUTH_CLIENT_IDS:
        raise GoogleTokenError('Token was issued for a different application.')

    # tokeninfo reports this as the string 'true', not a JSON boolean, so a truthiness test
    # would also accept the string 'false'.
    if str(claims.get('email_verified', '')).lower() != 'true':
        raise GoogleTokenError('Google has not verified that address.')

    if not claims.get('email'):
        raise GoogleTokenError('Token carries no email address.')

    required_domain = settings.GOOGLE_ALLOWED_HD
    if required_domain:
        _require_hosted_domain(access_token, required_domain)

    return claims


def _ask_google(url, params=None, headers=None):
    """Ask Google something about a token, or raise GoogleTokenError."""
    try:
        response = requests.get(url, params=params, headers=headers, timeout=GOOGLE_TIMEOUT)
    except requests.RequestException as err:
        raise GoogleTokenError('Could not reach Google.') from err

    if response.status_code != 200:
        raise GoogleTokenError('Google did not recognise that token.')

    try:
        return response.json()
    except ValueError as err:
        raise GoogleTokenError('Google returned something that was not readable.') from err


def _require_hosted_domain(access_token, required_domain):
    """Refuse unless Google attests this account belongs to the configured Workspace domain.

    `hd` is Google's own attestation of Workspace membership, and it describes the *account*,
    not the token - a token description carries no `hd` at all, so this asks userinfo rather
    than tokeninfo. The email address's own domain is never substituted for the attestation:
    anyone can hold a personal account whose address ends in the right characters.

    An account with no `hd` is refused. That is correct for a personal account, but it is also
    what a misconfiguration looks like from the outside - and every token-side refusal shares
    one response body by design - so the absent claim is logged. Without that, a restriction
    that refuses everyone would be indistinguishable from one working perfectly.
    """
    try:
        profile = _ask_google(
            USERINFO_URL, headers={'Authorization': f'Bearer {access_token}'}
        )
    except GoogleTokenError:
        # Logged for the same reason the absent claim below is: a restriction that refuses
        # everyone because the profile cannot be read looks, from outside, exactly like one
        # working perfectly.
        logger.warning(
            'Google signin refused: GOOGLE_ALLOWED_HD is %r but the account profile could '
            'not be read from Google.',
            required_domain,
        )
        raise
    hosted_domain = profile.get('hd')
    if not hosted_domain:
        logger.info(
            'Google signin refused: GOOGLE_ALLOWED_HD is %r but the account carries no '
            'hosted-domain attestation. Personal Google accounts never carry one.',
            required_domain,
        )
        raise GoogleTokenError('Account carries no hosted-domain attestation.')
    if hosted_domain.lower() != required_domain.lower():
        raise GoogleTokenError('Account is outside the permitted domain.')
