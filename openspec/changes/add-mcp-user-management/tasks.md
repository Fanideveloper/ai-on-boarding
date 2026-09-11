## 1. Shared password rule

- [x] 1.1 Add a maximum length of 128 to `validate_password_strength` in
  `sdd_django_demo/api/serializers.py`, with its own message naming the limit, separate from
  the existing minimum-strength message; verify by submitting a 129-character password to
  `POST /api/signup/` and seeing it refused with that message, and a 128-character one and
  seeing it accepted

## 2. Dependencies and configuration

- [x] 2.1 Add the HTTP client and settings-file loader to `sdd_django_demo/requirements.txt`,
  each pinned with a comment saying what it is for; verify `pip install -r requirements.txt`
  succeeds and `manage.py check` passes
- [x] 2.2 Add the Google settings to `sdd_django_demo/sdd_django_demo/settings.py`: the
  accepted client ids as a comma-separated list defaulting to empty, and the optional hosted
  domain defaulting to empty; verify `manage.py check` passes with neither variable set, so no
  contributor needs environment configuration to run or test the project
- [x] 2.3 Ignore the local settings file in `.gitignore`; verify `git status` does not offer to
  track it once created

## 3. Google sign-in

- [x] 3.1 Add `sdd_django_demo/api/google_auth.py`: ask Google to verify an access token, then
  check the audience is a configured client id, the email address is verified, and the hosted
  domain matches when one is configured; raise one error type for every refusal; verify by
  calling it directly against a stubbed Google response for each refusal
- [x] 3.2 Add `sdd_django_demo/api/mcp_views.py` with the Google sign-in endpoint: verify the
  token, resolve the single matching account, refuse an absent, ambiguous, or embargoed
  account, and return the same token signin returns; verify a stubbed valid token returns
  `{"token": ...}` and each refusal returns no token
- [x] 3.3 Give the endpoint one response body for every token-side refusal and one for every
  account-side refusal; verify two different refusals of each kind are byte-identical
- [x] 3.4 Add a rate limit on the endpoint keyed on the caller, refusing before the outbound
  call to Google; verify that attempts past the cap are refused and that the stubbed Google
  call is not reached for them

## 4. Account listing

- [x] 4.1 Add the account listing to `mcp_views.py`, restricted to administrators, returning
  username, country, and signup date and nothing else, including accounts with no recorded
  country; verify an administrator gets every account and that an entry for an account created
  outside signup carries an empty country
- [x] 4.2 Add the country and username filters, both matching without regard to case; verify
  each filter returns only matching accounts and that a differently-cased argument returns the
  same accounts

## 5. Password change

- [x] 5.1 Add the administrative password change to `mcp_views.py`, addressed by username,
  restricted to administrators, resolving the name without regard to case and refusing an
  ambiguous match; verify an administrator changes another account's password, a non-admin and
  an unauthenticated caller are both refused, an unknown name is refused, and an ambiguous name
  is refused
- [x] 5.2 Add the self-service password change to `mcp_views.py`, requiring the caller's
  current password alongside the new one; verify the correct current password succeeds and a
  wrong one is refused with the password unchanged
- [x] 5.3 Have both endpoints invalidate the affected account's existing authentication tokens;
  verify a token issued before the change is no longer accepted after it
- [x] 5.4 Route both endpoints' new password through the shared validator from task 1.1; verify
  a too-short, a letter-or-digit-less, and a too-long new password are each refused with the
  account's password unchanged
- [x] 5.5 Register all four routes in `sdd_django_demo/api/urls.py` and annotate each endpoint
  for the API schema; verify `GET /api/schema/` lists them with their success and refusal
  responses

## 6. MCP server

- [x] 6.1 Create `mcp_server/` at the repository root with its own pinned requirements and no
  import of Django; verify its dependencies install into a separate environment and that
  `pytest` in `sdd_django_demo/` does not collect anything from it
- [x] 6.2 Add `mcp_server/django_client.py` with one function that obtains the caller's
  authentication token by presenting their Google access token to the API; verify it returns a
  token for a stubbed successful response and raises for a stubbed refusal
- [x] 6.3 Give that client a per-call field allowlist applied to each API response before it is
  returned, so only the fields a tool needs leave the client; verify an extra field present in
  a stubbed response does not appear in the client's return value
- [x] 6.4 Have the client, on a refusal that says the held token is no longer accepted, obtain
  a fresh token and retry the request once before failing; verify a stubbed 401-then-success
  sequence returns the success, and a stubbed 401-then-401 sequence fails without a third
  attempt
- [x] 6.5 Translate each API refusal into a sentence stating what was refused and why, naming
  the maximum length when a password is refused for being too long, and directing a caller
  whose current password was wrong to the existing email reset flow; verify each stubbed
  refusal produces its own message
- [x] 6.6 Add the MCP server in `mcp_server/server.py` using the framework's Google
  authentication with its default behaviour - no override of its credential check, no caching,
  no self-signed token; verify the server starts and reports its tools
- [x] 6.7 Add the three tools - list accounts, list accounts from a country, change a password -
  each acting with the calling person's own token and reporting the API's actual verdict;
  verify against a stubbed API that a refused password change is reported as not changed

## 7. Tests (after implementation, from the spec)

- [x] 7.1 List every requirement in `specs/user-signup/spec.md`, `specs/user-signin/spec.md`,
  `specs/user-management/spec.md`, and `specs/mcp-server/spec.md`, with what a test would need
  to assert for each, working only from the specs
- [x] 7.2 Write the Django tests from that list in `sdd_django_demo/api/`, covering every
  requirement in the three Django-side specs, with a direct assertion for each
  security-sensitive behaviour - the privilege requirements, the identical refusals, the token
  invalidation, and the fields the listing must never disclose - rather than reaching them
  through a success path
- [x] 7.3 Write the MCP server's tests in `mcp_server/`, covering every requirement in
  `specs/mcp-server/spec.md` against a stubbed API, including that no disallowed field survives
  the client and that a refusal is never reported as a success
- [x] 7.4 Run `pytest` in `sdd_django_demo/` and confirm the whole suite passes, not only the
  new tests
- [x] 7.5 Run `pytest` in `mcp_server/` and confirm every test passes
- [x] 7.6 Prove at least one new test can fail: break the field allowlist so an email address
  survives the client, confirm the test asserting its absence goes red, then restore it

## 8. Traceability and review

- [x] 8.1 Build `traceability.md` mapping every requirement in all four specs to the code that
  satisfies it and the test that proves it
- [x] 8.2 Run `/code-review` and address every finding that cites a requirement, a named
  failing test, or a documented convention
- [x] 8.3 Run `/code-review` once more and record the verdict; proceed only on
  `Ready to merge: yes`
