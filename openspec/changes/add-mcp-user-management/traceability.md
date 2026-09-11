# Traceability

Every requirement in this change's four delta specs, the code that satisfies it, and the tests
that prove it.

Paths are relative to the repository root. Django tests run from `sdd_django_demo/`, MCP server
tests from `mcp_server/`; the two suites are separate and neither collects the other.

## user-signup (MODIFIED)

| Requirement | Code | Tests (`api/test_signup.py`) |
| --- | --- | --- |
| Enforce a minimum password strength | `sdd_django_demo/api/serializers.py` — `PASSWORD_MAX_LENGTH`, `validate_password_strength` | `test_signup_rejects_password_shorter_than_minimum`, `test_signup_rejects_password_without_digit`, `test_signup_rejects_password_without_letter`, `test_signup_rejects_password_longer_than_maximum`, `test_signup_accepts_password_at_the_maximum_length` |

The maximum lives in the one validator every path routes through, so password reset inherits it
with no change of its own — `user-password-reset`'s *Hold a new password to the signup strength
rules* is defined as the signup rules.

## user-signin (ADDED)

All code in `sdd_django_demo/api/google_auth.py` and `sdd_django_demo/api/mcp_views.py`; all
tests in `api/test_google_auth.py`.

| Requirement | Code | Tests |
| --- | --- | --- |
| Sign in with a verified Google access token | `verify_access_token`, `GoogleAuthView.post`; `mcp_server/server.py` — `required_scopes=['openid', 'email']`, without which Google returns no address and every signin is refused | `test_a_verified_token_for_a_matching_account_signs_in`, `test_the_same_account_may_sign_in_repeatedly`; `mcp_server/tests/test_server.py::test_the_server_asks_google_for_an_address_not_just_an_identifier` |
| Accept only a token issued for this application | `verify_access_token` audience check; `GOOGLE_OAUTH_CLIENT_IDS` in `settings.py` | `test_a_token_issued_for_another_application_is_refused`, `test_a_second_configured_client_id_is_accepted` |
| Require a verified email address | `verify_access_token` `email_verified` check | `test_an_unverified_address_is_refused` |
| Refuse an absent or ambiguous matching account | `resolve_google_user` | `test_a_token_matching_no_account_is_refused`, `test_a_token_matching_more_than_one_account_is_refused` |
| Refuse an embargoed account | `GoogleAuthView.post` via `embargo.rules.is_user_embargoed` | `test_an_embargoed_account_is_refused` |
| Restrict Google sign-in to a configured hosted domain | `_require_hosted_domain` (reads Google's userinfo endpoint, since `hd` describes the account and never appears in a token description); `GOOGLE_ALLOWED_HD` in `settings.py` | `test_a_matching_hosted_domain_signs_in`, `test_a_hosted_domain_differing_only_in_case_signs_in`, `test_a_non_matching_hosted_domain_is_refused`, `test_an_absent_hosted_domain_is_refused_when_one_is_required`, `test_an_absent_hosted_domain_is_fine_when_none_is_required`, `test_a_hosted_domain_restriction_reads_the_account_not_the_token`, `test_the_ordinary_path_asks_google_exactly_once` |
| Reject every Google-side refusal identically | `GOOGLE_REJECTION_BODY`, `GOOGLE_NO_ACCOUNT_BODY` | `test_two_different_token_side_refusals_are_indistinguishable`, `test_two_different_account_side_refusals_are_indistinguishable` |
| Never return a token in a Google sign-in rejection | `GoogleAuthView.post` | `test_no_rejection_carries_a_token_or_echoes_the_submitted_one` |
| Limit how often Google sign-in may be attempted | `GoogleSigninThrottle`; `google-signin` rate and `NUM_PROXIES` in `settings.py` | `test_attempts_beyond_the_cap_are_refused`, `test_a_refused_attempt_never_reaches_google`, `test_the_cap_cannot_be_walked_through_by_varying_a_forwarded_header` |

## user-management (NEW)

All code in `sdd_django_demo/api/mcp_views.py` and `sdd_django_demo/api/serializers.py`; all
tests in `api/test_user_management.py`.

| Requirement | Code | Tests |
| --- | --- | --- |
| List accounts | `UserListView`, `UserAccountSerializer` | `test_an_administrator_receives_every_account_with_its_country_and_signup_date` |
| Require administrative privileges to list accounts | `UserListView` — `TokenAuthentication`, `IsAdminUser` | `test_an_unauthenticated_caller_cannot_list_accounts`, `test_an_authenticated_non_administrator_cannot_list_accounts` |
| Filter the account listing by country | `UserListView.get_queryset` | `test_filtering_by_country_returns_only_those_accounts`, `test_a_country_differing_only_in_case_returns_the_same_accounts` |
| Filter the account listing by username | `UserListView.get_queryset` | `test_filtering_by_username_returns_only_that_account`, `test_a_username_differing_only_in_case_returns_the_same_account` |
| Include accounts with no recorded country | `UserAccountSerializer.get_country` | `test_an_account_created_outside_signup_appears_with_an_empty_country` |
| Never disclose an email address or an internal identifier in a listing | `UserAccountSerializer.Meta.fields` | `test_an_unfiltered_listing_discloses_no_address_and_no_identifier`, `test_a_filtered_listing_discloses_no_address_and_no_identifier` |
| Change any account's password as an administrator | `AdminChangePasswordView`; the self-service route lives at `/api/me/` rather than under `users/<username>/`, so no username is shadowed | `test_an_administrator_changes_another_accounts_password`, `test_an_account_named_me_is_still_addressable_by_an_administrator` |
| Require administrative privileges to change another account's password | `AdminChangePasswordView` — `TokenAuthentication`, `IsAdminUser` | `test_a_non_administrator_cannot_change_another_accounts_password`, `test_an_unauthenticated_caller_cannot_change_another_accounts_password` |
| Resolve the named account without regard to case | `resolve_named_user` | `test_an_account_named_in_a_different_case_is_still_found`, `test_a_name_matching_more_than_one_account_changes_nothing` |
| Reject a password change for an unknown account | `resolve_named_user` | `test_changing_the_password_of_an_unknown_account_is_refused` |
| Change one's own password | `SelfChangePasswordView`, `SelfChangePasswordSerializer`; served at `/api/me/change-password/` | `test_a_caller_changes_their_own_password`, `test_an_unauthenticated_caller_cannot_change_their_own_password` |
| Refuse a self-service change without the correct current password | `SelfChangePasswordView.post` | `test_a_wrong_current_password_changes_nothing` |
| Hold a changed password to the signup strength rules | Both change serializers use `validate_password_strength` | `test_an_administrative_change_refuses_a_password_signup_would_refuse`, `test_a_self_service_change_refuses_a_password_signup_would_refuse`, `test_an_administrative_change_refuses_a_password_above_the_maximum`, `test_a_self_service_change_refuses_a_password_above_the_maximum` |
| Invalidate existing authentication tokens on a password change | `set_password_and_revoke` | `test_an_administrative_change_invalidates_the_targets_token`, `test_a_self_service_change_invalidates_the_callers_own_token` |
| Never return a password | Both serializers' `write_only` fields; both views' response bodies | `test_a_successful_change_never_returns_a_password`, `test_a_refused_change_never_returns_a_password` |

## mcp-server (NEW)

Code in `mcp_server/`; tests in `mcp_server/tests/`.

| Requirement | Code | Tests |
| --- | --- | --- |
| Act with the calling person's own privileges | `server.py` — `client_for_access_token` (module level, so the seam is testable); `django_client.py` — `_api_token_for_caller` | `test_server.py::test_the_client_carries_the_callers_own_token_not_a_shared_one`, `::test_two_callers_do_not_share_a_credential`, `::test_a_request_with_no_identity_is_refused_rather_than_acted_on`; `test_django_client.py::test_the_callers_own_google_token_buys_the_api_token_used_for_every_request`, `::test_a_google_account_with_no_account_here_is_refused`, `::test_an_unreachable_account_service_is_reported_not_raised_raw`; privilege outcome at the tool level in `::test_a_listing_refused_to_a_non_administrator_says_so` (refused) and `test_tools.py::test_the_listing_tool_returns_every_account` (allowed) |
| Expose a tool that lists accounts | `server.py` — `list_users`; `tools.py` — `list_accounts` | `test_tools.py::test_the_listing_tool_returns_every_account`; `test_server.py::test_the_server_publishes_exactly_the_three_tools` |
| Expose a tool that lists accounts from a country | `server.py` — `list_users_by_country`; `tools.py` — `list_accounts_from_country` | `test_tools.py::test_the_country_tool_returns_only_accounts_from_that_country`, `::test_a_country_named_in_a_different_case_returns_the_same_accounts`, `::test_an_empty_country_is_refused_before_the_api_is_called`; `test_django_client.py::test_a_country_is_passed_through_as_a_filter`; `test_server.py::test_the_server_publishes_exactly_the_three_tools` |
| Expose a tool that changes a password | `server.py` — `change_password`; `tools.py` — `change_password` (a current password means your own account, a username means somebody else's, both together are refused rather than guessed at) | `test_tools.py::test_omitting_a_username_changes_the_callers_own_password`, `::test_naming_an_account_changes_that_accounts_password`, `::test_giving_both_a_username_and_a_current_password_is_refused_not_guessed`, `::test_changing_your_own_password_without_the_current_one_is_refused_locally`, `::test_an_empty_username_is_treated_as_the_callers_own_account`; `test_django_client.py::test_a_username_is_encoded_before_it_reaches_the_url` (the name reaches a URL path segment from the assistant, so it is encoded); `test_server.py::test_the_server_publishes_exactly_the_three_tools` |
| Disclose only the fields a tool needs | `django_client.py` — `ACCOUNT_FIELDS`, `_only` | `test_django_client.py::test_no_field_beyond_the_allowlist_survives_the_client`, `::test_a_field_the_api_adds_later_does_not_begin_reaching_the_assistant`, `::test_an_allowed_field_the_api_omits_comes_back_empty_rather_than_missing` |
| Report the account system's actual verdict | `django_client.py` — status checks on every call; `tools.py` — `change_password` returns only after the call succeeds | `test_tools.py::test_a_refused_password_change_is_never_reported_as_a_success`, `::test_a_successful_action_passes_through_run_action_unchanged` |
| State a refusal in plain language | `django_client.py` — `_body` (classifies by the field the API keyed its error on, not by words in the message), `_listing_refusal`, `_admin_change_refusal`, `_self_change_refusal`, `_detail`; `server.py` — `run_action` | `test_django_client.py::test_a_listing_refused_to_a_non_administrator_says_so`, `::test_a_password_refused_for_its_length_names_the_maximum`, `::test_an_unknown_account_is_named_in_the_refusal`, `::test_an_ambiguous_username_is_not_reported_as_a_rejected_password`, `::test_a_rejected_new_password_is_classified_by_its_field_not_its_wording`, `::test_an_unreadable_refusal_body_does_not_break_the_wording`, `::test_a_refusal_body_cannot_flood_the_assistant`, `::test_an_unexpected_200_is_reported_rather_than_escaping`, `::test_an_unparseable_400_is_not_reported_as_a_wrong_current_password`; `test_tools.py::test_a_refusal_reaches_the_assistant_as_the_frameworks_own_error` |
| Point a caller who lacks their current password at the reset flow | `django_client.py` — `_self_change_refusal`, `FORGOTTEN_PASSWORD_ADVICE`; `tools.py` — `change_password` | `test_django_client.py::test_a_wrong_current_password_points_at_the_email_reset_flow`, `::test_a_missing_current_password_is_not_reported_as_a_rejected_new_password`, `::test_a_reworded_wrong_current_password_is_still_recognised`; `test_tools.py::test_changing_your_own_password_without_the_current_one_is_refused_locally` |
| Obtain a fresh authentication token once before failing | `django_client.py` — `_request` | `test_django_client.py::test_a_token_the_api_stopped_accepting_is_replaced_and_the_request_retried`, `::test_a_second_refusal_is_reported_rather_than_retried_again` |

## Falsifiability

Task 7.6: the field allowlist in `django_client.py` was replaced with a pass-through, the suite
was re-run, and exactly the three tests asserting the allowlist went red — including
`test_no_field_beyond_the_allowlist_survives_the_client`, whose failure named `'email'` among
the fields that had survived. The allowlist was then restored and the suite passed again.

## Review

Five passes of `/code-review`. Eleven blocking findings across the first four, every one fixed
and each carrying a test that fails without its fix. The fifth pass, run against the trimmed
tree, found nothing meeting the blocking bar and returned `Ready to merge: yes`.

| # | Finding | Cited |
| --- | --- | --- |
| 1 | The sign-in cap keyed on a caller-supplied `X-Forwarded-For`, so varying it bypassed the cap entirely | `user-signin` — *Limit how often Google sign-in may be attempted* |
| 2 | An ambiguous username was reported as a rejected password | `mcp-server` — *State a refusal in plain language* |
| 3 | The self-service refusal was classified by searching for words in the message | `mcp-server` — *State a refusal in plain language* |
| 4 | Tool routing stranded a non-administrator who named their own account; the first fix then stranded the administrator instead, silently changing their own password | `mcp-server` — *Expose a tool that changes a password* |
| 5 | `users/me/change-password/` shadowed an account named `me` | `user-management` — *Change any account's password as an administrator* |
| 6 | The hosted-domain check read `hd` from a token description, which never carries it | `user-signin` — *Restrict Google sign-in to a configured hosted domain* |
| 7 | `GoogleProvider` defaulted to the `openid` scope alone, which returns no address — every sign-in would have been refused in production while the whole suite stayed green | `user-signin` — *Sign in with a verified Google access token* |
| 8 | The seam deciding whose credential a tool acts with had no test; a shared server credential left all 33 tests passing | `mcp-server` — *Act with the calling person's own privileges*; config.yaml's direct-test rule |
| 9 | This file cited a test deleted by fix 4 and described the behaviour it reversed | config.yaml — traceability |
| 10 | `mcp_server/tests/test_server.py` was left untracked; committing the index would have dropped fix 8 | config.yaml — traceability, direct tests |
| 11 | Two rationales written here were wrong on checking: the password cap was justified as a denial-of-service fix (measurement showed hashing cost is independent of password length), and `server.py` claimed the server "mints nothing of its own" (the framework mints JWTs and persists Google refresh tokens to an encrypted on-disk store) | — corrected in `proposal.md`, `design.md`, `server.py`, and documented in `mcp_server/README.md` |

Recorded, deliberately not acted on: Google sign-in does not check `is_active`, where password
sign-in does. The token issued is unusable — `TokenAuthentication` rejects an inactive user —
but a deactivated account answers 200 where an unknown address answers 403, which is
observable. No requirement here names `is_active`, so implementing it would be behaviour the
specs do not describe; it needs a requirement first. Also recorded: all MCP callers share one
sign-in bucket, and the self-service change is unthrottled.

Not verifiable here: that Google's userinfo endpoint returns `hd`. Confirming it needs a real
Workspace account, and the tests stub Google. What *is* settled is that the endpoint it
replaced does not return it.

## Trim

Removed as not earning their place, with no change to behaviour: the `username` filter on
`DjangoClient.list_accounts` (no tool reached it, and the mcp-server spec defines none that
would); `mcp_server/tests/__init__.py` (`conftest.py` already puts the modules on the path);
and two pairs of tests folded into one each, where the spec had one scenario between them.
Every test is cited above against the requirement it protects, and every citation is verified
to exist.

Recorded from the final pass, non-blocking: the administrative change validates the new
password before resolving the username, so an unknown account named together with a weak
password is reported as a rejected password rather than an unknown account (the request is
refused either way, and no scenario names the ordering); and `StubClient.list_accounts` in
`test_tools.py` still accepts a `username` argument the real client no longer takes.

