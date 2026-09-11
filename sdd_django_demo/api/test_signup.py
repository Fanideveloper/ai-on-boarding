from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from embargo.models import AccountCountry


@pytest.fixture
def client():
    return APIClient()


def signup(client, email='ada@example.com', username='ada', password='lovelace1', country='France'):
    return client.post(
        '/api/signup/',
        {'email': email, 'username': username, 'password': password, 'country': country},
        format='json',
    )


@pytest.mark.django_db
def test_signup_requires_email(client):
    response = client.post(
        '/api/signup/',
        {'username': 'ada', 'password': 'lovelace1', 'country': 'France'},
        format='json',
    )

    assert response.status_code == 400
    assert 'email' in response.data


@pytest.mark.django_db
def test_signup_requires_password(client):
    response = client.post(
        '/api/signup/',
        {'email': 'ada@example.com', 'username': 'ada', 'country': 'France'},
        format='json',
    )

    assert response.status_code == 400
    assert 'password' in response.data


@pytest.mark.django_db
def test_signup_requires_username(client):
    response = client.post(
        '/api/signup/',
        {'email': 'ada@example.com', 'password': 'lovelace1', 'country': 'France'},
        format='json',
    )

    assert response.status_code == 400
    assert 'username' in response.data


@pytest.mark.django_db
def test_signup_requires_country(client):
    response = client.post(
        '/api/signup/',
        {'email': 'ada@example.com', 'username': 'ada', 'password': 'lovelace1'},
        format='json',
    )

    assert response.status_code == 400
    assert 'country' in response.data


@pytest.mark.django_db
def test_signup_rejects_country_over_max_length(client):
    response = signup(client, country='A' * 101)

    assert response.status_code == 400
    assert 'country' in response.data
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_signup_rejects_blocked_country(client):
    response = signup(client, country='India')

    assert response.status_code == 400
    assert 'country' in response.data
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_signup_allows_unblocked_country(client):
    response = signup(client, country='France')

    assert response.status_code == 200


@pytest.mark.django_db
def test_signup_persists_submitted_country(client):
    """Signin's embargo re-check reads this record, not anything from signup time."""
    signup(client, country='France')

    user = User.objects.get()
    assert AccountCountry.objects.get(user=user).country == 'france'


@pytest.mark.django_db
def test_signup_rejects_malformed_email(client):
    response = signup(client, email='not-an-email')

    assert response.status_code == 400
    assert 'email' in response.data


@pytest.mark.django_db
def test_signup_rejects_duplicate_email(client):
    signup(client, email='ada@example.com', username='ada1')

    response = signup(client, email='ada@example.com', username='ada2', password='lovelace2')

    assert response.status_code == 400
    assert 'email' in response.data
    assert User.objects.filter(email='ada@example.com').count() == 1


@pytest.mark.django_db
def test_signup_duplicate_email_is_case_insensitive(client):
    signup(client, email='Ada@Example.com', username='ada1')

    response = signup(
        client, email='ADA@EXAMPLE.COM', username='ada2', password='lovelace2'
    )

    assert response.status_code == 400
    assert User.objects.filter(email='ada@example.com').count() == 1


@pytest.mark.django_db
def test_signup_normalises_email_to_lowercase(client):
    response = signup(client, email='Ada@Example.com')

    assert response.data['email'] == 'ada@example.com'
    assert User.objects.get().email == 'ada@example.com'


@pytest.mark.django_db
def test_signup_duplicate_email_race_returns_400_not_500(client):
    User.objects.create_user(username='someoneelse', email='ada@example.com', password='lovelace1')

    with patch('api.serializers.User.objects.filter') as mock_filter:
        mock_filter.return_value.exists.return_value = False
        response = signup(client, email='ada@example.com', username='newada', password='lovelace2')

    assert response.status_code == 400
    assert 'email' in response.data
    assert User.objects.filter(email='ada@example.com').count() == 1


@pytest.mark.django_db
def test_signup_rejects_password_shorter_than_minimum(client):
    response = signup(client, password='abc123')

    assert response.status_code == 400
    assert 'password' in response.data


@pytest.mark.django_db
def test_signup_rejects_password_without_digit(client):
    response = signup(client, password='noDigitsHere')

    assert response.status_code == 400
    assert 'password' in response.data


@pytest.mark.django_db
def test_signup_rejects_password_without_letter(client):
    response = signup(client, password='12345678')

    assert response.status_code == 400
    assert 'password' in response.data


@pytest.mark.django_db
def test_signup_rejects_password_longer_than_maximum(client):
    response = signup(client, password='a1' + 'x' * 127)

    assert response.status_code == 400
    assert 'password' in response.data
    # The message has to name the bound: it is the one thing the person can act on without
    # guessing, and it is what the assistant calling this API repeats back to them.
    assert 'at most 128' in str(response.data['password'])


@pytest.mark.django_db
def test_signup_accepts_password_at_the_maximum_length(client):
    response = signup(client, password='a1' + 'x' * 126)

    assert response.status_code == 200
    assert User.objects.filter(username='ada').exists()


@pytest.mark.django_db
def test_signup_creates_exactly_one_account(client):
    signup(client)

    assert User.objects.count() == 1


@pytest.mark.django_db
def test_signup_stores_password_hashed_not_plaintext(client):
    signup(client, password='lovelace1')

    user = User.objects.get()
    assert user.password != 'lovelace1'
    assert user.check_password('lovelace1')


@pytest.mark.django_db
def test_signup_response_never_contains_password(client):
    response = signup(client, password='lovelace1')

    assert 'password' not in response.data
    assert 'lovelace1' not in response.content.decode()


@pytest.mark.django_db
def test_signup_success_returns_200_with_email_and_username(client):
    response = signup(client, email='ada@example.com', username='ada')

    assert response.status_code == 200
    assert response.data == {'email': 'ada@example.com', 'username': 'ada'}


@pytest.mark.django_db
def test_signup_rejects_username_too_short(client):
    response = signup(client, username='ab')

    assert response.status_code == 400
    assert 'username' in response.data


@pytest.mark.django_db
def test_signup_rejects_username_too_long(client):
    response = signup(client, username='a' * 31)

    assert response.status_code == 400
    assert 'username' in response.data


@pytest.mark.django_db
def test_signup_rejects_username_with_disallowed_character(client):
    response = signup(client, username='ada-lovelace')

    assert response.status_code == 400
    assert 'username' in response.data


@pytest.mark.django_db
def test_signup_rejects_duplicate_username(client):
    signup(client, email='ada1@example.com', username='ada')

    response = signup(client, email='ada2@example.com', username='ada', password='lovelace2')

    assert response.status_code == 400
    assert 'username' in response.data
    assert User.objects.filter(username='ada').count() == 1


@pytest.mark.django_db
def test_signup_duplicate_username_is_case_insensitive(client):
    signup(client, email='ada1@example.com', username='Ada')

    response = signup(client, email='ada2@example.com', username='ADA', password='lovelace2')

    assert response.status_code == 400
    assert User.objects.filter(username='ada').count() == 1


@pytest.mark.django_db
def test_signup_normalises_username_to_lowercase(client):
    response = signup(client, username='Ada')

    assert response.data['username'] == 'ada'
    assert User.objects.get().username == 'ada'


@pytest.mark.django_db
def test_signup_duplicate_username_race_returns_400_not_500(client):
    User.objects.create_user(username='ada', email='someoneelse@example.com', password='lovelace1')

    with patch('api.serializers.User.objects.filter') as mock_filter:
        mock_filter.return_value.exists.return_value = False
        response = signup(client, email='newada@example.com', username='ada', password='lovelace2')

    assert response.status_code == 400
    assert 'username' in response.data
    assert User.objects.filter(username='ada').count() == 1
