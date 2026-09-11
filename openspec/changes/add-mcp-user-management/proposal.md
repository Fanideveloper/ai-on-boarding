## Why

The API can only be driven by a person with a password. There is no way for an assistant to
answer "who has signed up?", "who signed up from Pakistan?", or "change this account's
password" on someone's behalf, and no way for a caller to sign in with a Google account they
already have. This change adds the account-management surface those questions need, and an MCP
server that exposes them as tools.

## What Changes

- Add Google sign-in: a caller who has already completed a Google login elsewhere can exchange
  the resulting Google access token for the same authentication token password signin returns.
  The system verifies the token with Google rather than performing the login itself, so it
  never holds a Google client secret.
- Add an admin-only listing of accounts, showing each account's username, country, and signup
  date, filterable by country or by username, both case-insensitively.
- Add an admin-only password change for any named account.
- Add a self-service password change: an authenticated caller supplies their current password
  and a new one. Both password changes invalidate the affected account's existing
  authentication tokens.
- **BREAKING** Reject a password longer than 128 characters. This applies wherever a password
  is accepted - signup, reset, and both new password changes - and the refusal names the
  limit. Today a password of any length is accepted, so nothing bounds what a caller may
  submit or what a request body carries; 128 characters is comfortably above any usable
  passphrase.
- Limit how often Google sign-in may be attempted, so an unauthenticated caller cannot use it
  to generate unbounded outbound traffic.
- Add an MCP server exposing three tools: list accounts, list accounts by country, and change
  a password. Tools report the system's actual verdict - a refusal is never presented as a
  success - and refusals are stated in plain language rather than as a bare status code.

## Capabilities

### New Capabilities

- `user-management`: viewing and modifying existing accounts - the account listing, its
  filters, what an account listing may and may not disclose, admin-initiated password change,
  and self-service password change.
- `mcp-server`: the MCP tool surface - which tools exist, what each returns, which fields may
  reach the caller, and how a refusal is reported.

### Modified Capabilities

- `user-signin`: gains Google sign-in as a second way to obtain an authentication token,
  alongside the existing email-and-password submission.
- `user-signup`: `Enforce a minimum password strength` gains an upper bound - a password
  longer than 128 characters is refused. Password reset inherits this unchanged, because its
  rules are defined as the signup rules.

## Impact

- New endpoints under `sdd_django_demo/api/`: `POST /api/auth/google/`, `GET /api/users/`,
  `POST /api/users/<username>/change-password/`, `POST /api/me/change-password/`.
- Existing password validation gains a maximum length, so signup and password reset both
  start refusing submissions they previously accepted.
- New top-level `mcp_server/` - a separate process that talks to the API over HTTP. It does
  not import Django and is not part of the Django test suite.
- New dependencies: an HTTP client and a settings loader on the Django side for the Google
  verification call; FastMCP on the MCP side.
- New configuration on the API side: the Google client id(s) a token may name as its
  audience, and an optional restriction to a single hosted domain. No client secret is needed
  there, because the API verifies a token rather than obtaining one.
- New configuration on the MCP server side: the address of the API, this server's own public
  address, and a Google client id and secret. The secret is needed there - completing a Google
  login is exactly what that side does - and the MCP framework also derives its own token
  signing and storage keys from it.
- Deliberately excluded, and recorded so they are not mistaken for oversights: caching the
  authentication token between tool calls, minting a signed token of the MCP server's own,
  and bypassing the MCP framework's own credential check. Each is a performance optimisation,
  none is needed for correct behaviour.
