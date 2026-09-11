"""Endpoints that exist to serve the MCP server, not the browser-facing account flows.

Google signin, the account listing, and both password changes have no caller but the MCP
server: a person signing in through a browser goes through SigninView, and only the MCP server
holds a Google OAuth client. Keeping them out of views.py leaves that file to the account
lifecycle - signup, signin, password reset - every caller uses.

Authorisation is decided here rather than in the MCP server. An assistant can be talked out of
a policy check, and anyone can call these endpoints directly without going through the MCP
server at all, so the MCP server is a convenience layer and this is the boundary.
"""

from django.contrib.auth.models import User
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import generics
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from embargo.rules import is_user_embargoed

from .google_auth import GoogleTokenError, verify_access_token
from .serializers import (
    AdminChangePasswordSerializer,
    GoogleAuthSerializer,
    SelfChangePasswordSerializer,
    TokenSerializer,
    UserAccountSerializer,
)

# One body for every way the token itself can be refused - unrecognised by Google, wrong
# audience, unverified address, wrong hosted domain, Google unreachable - so the response
# cannot be used to tell them apart.
#
# A template, not a response body: `Response(...)` keeps whatever dict it is handed, so passing
# the constant itself would leave `response.data` referring to this module-level dict, and any
# renderer or test that mutated it would corrupt the constant for the life of the process. Same
# reasoning as views.py's reset constants; each response gets its own copy.
GOOGLE_REJECTION_BODY = {'detail': 'Unable to sign in with that Google account.'}

# Separate from the body above, and deliberately so: the token was fine, the account is the
# problem - no match, more than one match, or an embargoed account. One body for all three, so
# the response cannot be used to discover which addresses have accounts here.
GOOGLE_NO_ACCOUNT_BODY = {'detail': 'That Google account cannot sign in here.'}


class GoogleSigninThrottle(SimpleRateThrottle):
    """Cap how often one caller may attempt Google signin.

    Keyed on the caller rather than on an address, because the address a token belongs to is
    not known until Google has been asked - which is the very call this limit exists to bound.
    DRF applies throttles in `initial()`, before the handler runs, so a refused attempt never
    reaches Google.
    """

    scope = 'google-signin'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


def resolve_google_user(email):
    """The single account a verified Google address signs in as, or None.

    Refuses an ambiguous match rather than choosing. `User.email` carries no uniqueness
    constraint, and accounts created outside signup are not lowercased, so a case-insensitive
    match can genuinely return more than one row - and picking one would hand the caller a
    token for an account that is not theirs.
    """
    matches = list(User.objects.filter(email__iexact=email).order_by('pk')[:2])
    if len(matches) != 1:
        return None
    return matches[0]


class GoogleAuthView(generics.GenericAPIView):
    """Sign in with a Google access token the caller obtained elsewhere.

    A second door onto the same room as SigninView: what comes out is the same authentication
    token, so every other endpoint is unaffected and there is no second credential format to
    reason about.
    """

    serializer_class = GoogleAuthSerializer
    throttle_classes = [GoogleSigninThrottle]

    @extend_schema(
        request=GoogleAuthSerializer,
        responses={
            200: OpenApiResponse(response=TokenSerializer, description='Signed in.'),
            401: OpenApiResponse(
                description=(
                    'The token was refused: unrecognised, issued for another application, '
                    'carrying an unverified address, outside the permitted hosted domain, or '
                    'Google could not be reached. Identical in status and body for all of them.'
                )
            ),
            403: OpenApiResponse(
                description=(
                    'The token verified, but no single account here can sign in with it: no '
                    'match, more than one match, or an embargoed account. Identical in status '
                    'and body for all three.'
                )
            ),
            429: OpenApiResponse(description='Too many Google signin attempts from this caller.'),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            claims = verify_access_token(serializer.validated_data['access_token'])
        except GoogleTokenError:
            return Response(dict(GOOGLE_REJECTION_BODY), status=401)

        user = resolve_google_user(claims['email'])
        if user is None or is_user_embargoed(user):
            return Response(dict(GOOGLE_NO_ACCOUNT_BODY), status=403)

        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key}, status=200)


class UserListView(generics.ListAPIView):
    """The account listing, for administrators only.

    Restricted because usernames, countries and signup dates together are an aggregate of
    personal data, and because it keeps one rule across this module: an administrator sees
    every account, anyone else sees only themselves.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAdminUser]
    serializer_class = UserAccountSerializer

    def get_queryset(self):
        # Ordered, so two identical requests return the same accounts in the same order rather
        # than whatever the database happened to yield.
        queryset = User.objects.select_related('accountcountry').order_by('pk')
        country = self.request.query_params.get('country')
        if country:
            # `iexact`, because countries are stored lowercased but a caller naming one has no
            # reason to know that.
            queryset = queryset.filter(accountcountry__country__iexact=country)
        username = self.request.query_params.get('username')
        if username:
            # `iexact` for the same reason, and to match how the administrative password change
            # resolves the name a caller read out of this listing.
            queryset = queryset.filter(username__iexact=username)
        return queryset

    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=UserAccountSerializer(many=True),
                description=(
                    'One entry per account, carrying a username, the country recorded at '
                    'signup, and the signup date. Never an email address or an internal id.'
                ),
            ),
            401: OpenApiResponse(description='No valid authentication token.'),
            403: OpenApiResponse(description='Caller is not an administrator.'),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


PASSWORD_CHANGED_BODY = {'detail': 'Password changed.'}
NO_SUCH_ACCOUNT_BODY = {'detail': 'No account with that username.'}
AMBIGUOUS_ACCOUNT_BODY = {'detail': 'More than one account matches that username.'}
WRONG_CURRENT_PASSWORD_BODY = {'detail': 'Current password is incorrect.'}


def resolve_named_user(username):
    """Find the one account a caller named, or the refusal explaining why not.

    Matched without regard to case, because the listing matches usernames that way too and an
    account named out of a listing has to be reachable in the case the listing reported.
    Django's uniqueness on username is case-sensitive, so a case-insensitive match can return
    more than one row - and picking one would change a password on an account the caller did
    not name. Returns `(user, None)` or `(None, response)`.
    """
    matches = list(User.objects.filter(username__iexact=username).order_by('pk')[:2])
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, Response(dict(NO_SUCH_ACCOUNT_BODY), status=404)
    return None, Response(dict(AMBIGUOUS_ACCOUNT_BODY), status=400)


def set_password_and_revoke(user, new_password):
    """Set a password and retire every token already issued for that account.

    One transaction, so a failure part-way cannot leave the password changed while tokens
    issued against the old one stay usable. The same pairing password reset already makes -
    changing a password is what invalidates the credentials derived from it.
    """
    with transaction.atomic():
        user.set_password(new_password)
        user.save(update_fields=['password'])
        Token.objects.filter(user=user).delete()


class AdminChangePasswordView(generics.GenericAPIView):
    """Set any account's password, for administrators only.

    Addressed by username rather than by an internal id, so the listing never has to disclose
    one. No current password is required: an administrator resetting an account is precisely
    the case where nobody knows it.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAdminUser]
    serializer_class = AdminChangePasswordSerializer

    @extend_schema(
        request=AdminChangePasswordSerializer,
        responses={
            200: OpenApiResponse(description='Password changed.'),
            400: OpenApiResponse(
                description='The new password was rejected, or the name matched more than one '
                            'account.'
            ),
            401: OpenApiResponse(description='No valid authentication token.'),
            403: OpenApiResponse(description='Caller is not an administrator.'),
            404: OpenApiResponse(description='No account with that username.'),
        },
    )
    def post(self, request, username, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, refusal = resolve_named_user(username)
        if refusal is not None:
            return refusal
        set_password_and_revoke(user, serializer.validated_data['password'])
        return Response(dict(PASSWORD_CHANGED_BODY), status=200)


class SelfChangePasswordView(generics.GenericAPIView):
    """Replace one's own password, given the current one.

    The current password is required even though the caller already holds a valid token. A
    token that has been stolen would otherwise be enough to take an account over, and token
    invalidation on change - the thing that contains a stolen token - would be defeated by the
    very credential it exists to revoke.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = SelfChangePasswordSerializer

    @extend_schema(
        request=SelfChangePasswordSerializer,
        responses={
            200: OpenApiResponse(
                description='Password changed. The caller\'s own tokens are now invalid.'
            ),
            400: OpenApiResponse(
                description='The current password was wrong, or the new password was rejected.'
            ),
            401: OpenApiResponse(description='No valid authentication token.'),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data['current_password']):
            return Response(dict(WRONG_CURRENT_PASSWORD_BODY), status=400)
        set_password_and_revoke(request.user, serializer.validated_data['new_password'])
        return Response(dict(PASSWORD_CHANGED_BODY), status=200)
