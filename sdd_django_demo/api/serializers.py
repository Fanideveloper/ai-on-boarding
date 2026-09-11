import re

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from embargo.rules import is_blocked, record_account_country

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 30
USERNAME_RE = re.compile(r'^[A-Za-z0-9_]+$')


def validate_password_strength(value):
    # Judged before the strength rules below, and reported separately, so someone who
    # submitted an over-long password is told that is the problem rather than being told
    # to add a letter and a digit to a password that already has both.
    if len(value) > PASSWORD_MAX_LENGTH:
        raise serializers.ValidationError(
            f'Must be at most {PASSWORD_MAX_LENGTH} characters.'
        )
    if (
        len(value) < PASSWORD_MIN_LENGTH
        or not re.search(r'[A-Za-z]', value)
        or not re.search(r'\d', value)
    ):
        raise serializers.ValidationError(
            f'Must be at least {PASSWORD_MIN_LENGTH} characters and contain a letter and a digit.'
        )


def validate_username_format(value):
    if not USERNAME_RE.fullmatch(value):
        raise serializers.ValidationError(
            'Must contain only letters, digits, or underscores.'
        )


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, allow_blank=False)
    username = serializers.CharField(
        required=True,
        allow_blank=False,
        min_length=USERNAME_MIN_LENGTH,
        max_length=USERNAME_MAX_LENGTH,
        validators=[validate_username_format],
    )
    password = serializers.CharField(
        required=True, allow_blank=False, write_only=True, validators=[validate_password_strength]
    )
    country = serializers.CharField(required=True, allow_blank=False, max_length=100)

    def validate_email(self, value):
        normalised = value.lower()
        if User.objects.filter(email=normalised).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return normalised

    def validate_username(self, value):
        normalised = value.lower()
        if User.objects.filter(username=normalised).exists():
            raise serializers.ValidationError('An account with this username already exists.')
        return normalised
    def validate_country(self, value):
        if is_blocked(value):
            raise serializers.ValidationError('Signups from this country are not allowed.')
        return value

    def create(self, validated_data):
        email = validated_data['email']
        username = validated_data['username']
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username, email=email, password=validated_data['password']
                )
                record_account_country(user, validated_data['country'])
                return user
        except IntegrityError as err:
            message = str(err)
            if 'username' in message:
                field = 'username'
            elif 'email' in message:
                field = 'email'
            else:
                raise
            raise serializers.ValidationError(
                {field: [f'An account with this {field} already exists.']}
            )


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'username']


class SigninSerializer(serializers.Serializer):
    email_or_username = serializers.CharField(required=True, allow_blank=False, max_length=255)
    password = serializers.CharField(required=True, allow_blank=False, write_only=True)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, allow_blank=False)


class PasswordResetConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(required=True, allow_blank=False)
    password = serializers.CharField(
        required=True, allow_blank=False, write_only=True, validators=[validate_password_strength]
    )


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField()


class GoogleAuthSerializer(serializers.Serializer):
    access_token = serializers.CharField(required=True, allow_blank=False, write_only=True)


class UserAccountSerializer(serializers.ModelSerializer):
    """How one account appears in the listing.

    Neither `id` nor `email` is exposed. The administrative password change addresses an
    account by username rather than by an internal id, so no caller needs the id; and an
    address is the one piece of personal data a caller listing accounts has no need to see.
    Both omissions are requirements, not house style - see the change's user-management spec.
    """

    country = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['username', 'country', 'date_joined']

    # Declared explicitly because the schema is what the MCP server reads: without it
    # drf-spectacular infers a plain non-nullable string, and an account created outside
    # signup would come back null against a schema that said it could not.
    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_country(self, obj):
        # An account created outside signup - by createsuperuser, the admin, or a shell - has
        # no country row at all. It still belongs in an administrative listing, so the country
        # comes back empty rather than the account being dropped. The reverse one-to-one
        # raises AttributeError when absent, which is what getattr's default catches.
        account_country = getattr(obj, 'accountcountry', None)
        return account_country.country if account_country else None


class AdminChangePasswordSerializer(serializers.Serializer):
    password = serializers.CharField(
        required=True, allow_blank=False, write_only=True, validators=[validate_password_strength]
    )


class SelfChangePasswordSerializer(serializers.Serializer):
    # The current password carries no strength validator: it is being checked, not chosen, and
    # an account whose password predates a rule still has to be able to prove it knows it.
    current_password = serializers.CharField(required=True, allow_blank=False, write_only=True)
    new_password = serializers.CharField(
        required=True, allow_blank=False, write_only=True, validators=[validate_password_strength]
    )
