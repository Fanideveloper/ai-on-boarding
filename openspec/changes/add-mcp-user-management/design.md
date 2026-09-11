## Context

See proposal.md - Why. Constraints that shape the approach:

- Accounts are `django.contrib.auth.User`. Signup lowercases both email and username, but
  accounts created outside signup are not normalised, and `email` carries no uniqueness
  constraint. Any lookup by email or username must cope with both.
- The country recorded at signup lives in the embargo app, written only by signup. Accounts
  created outside signup have no country row at all.
- Authentication today is an opaque token issued by signin. Password reset already deletes an
  account's tokens when its password changes, so token invalidation on password change is an
  established behaviour to match rather than invent.
- The MCP server is a second process. It talks to the API over HTTP and must not import
  Django.

## Goals / Non-Goals

**Goals:**

- One place where password strength is decided, so every path that sets a password inherits
  the same rules.
- Authorization decided by the API, never by the MCP server.
- One seam through which the MCP server obtains an authentication token.

**Non-Goals:**

- Caching the account API's authentication token between tool calls.
- Adding a signed token of our own design, on top of what the MCP framework already issues.
- Replacing the MCP framework's own credential check with a local signature check.
- Deciding, for any future cached or self-signed token, whether it would carry the
  authentication token inside it or look it up.

Each is a latency optimisation. None is needed for any requirement in this change, and each
adds a credential lifetime to reason about. They are listed so a later reader knows they were
considered and declined, not overlooked.

One correction to how the second of those reads: taking the framework's defaults is not the
same as no token being minted. Its OAuth proxy issues JWTs of its own, signed with a key
derived from the Google client secret, and persists each caller's upstream Google tokens -
refresh tokens included, since the provider requests offline access - to an encrypted on-disk
store. What this change declines is adding a *further* token of its own design; the framework's
own credentials are accepted as they come, and a deployment owns the directory they live in.

## Decisions

**Verify the Google token; never exchange an authorization code.**
Satisfies `user-signin` - *Sign in with a verified Google access token*. The caller completes
the Google login and sends the resulting access token; the API asks Google whether that token
is good. The alternative, redeeming an authorization code, requires holding a Google client
secret, which buys nothing here because the caller has already done the interactive half.

**Return the existing opaque authentication token, not a new token type.**
Satisfies the same requirement's "same authentication token an email-and-password signin
returns". Every existing endpoint keeps working unchanged and there is no second credential
format to reason about. A signed token was the alternative; it would be faster to check but
cannot be revoked before it expires, and *Invalidate existing authentication tokens on a
password change* depends on revocation being immediate.

**Configure the accepted audience as a list of client ids.**
Satisfies `user-signin` - *Accept only a token issued for this application*. A list means the
MCP server can later be registered separately from any other client without changing how the
check works - only what it is configured with.

**Put the maximum length in the single shared password validator.**
Satisfies the modified `user-signup` - *Enforce a minimum password strength* and
`user-management` - *Hold a changed password to the signup strength rules*. Signup, reset, and
both password changes already route through one validator; extending it means one rule in one
place. Checking length per endpoint was the alternative and is how the four paths drift apart.

**Two password-change endpoints, not one with a target parameter.**
Satisfies `user-management` - *Change one's own password*, *Change any account's password as
an administrator*, and *Require administrative privileges to change another account's
password*. Separate addresses mean the privilege requirement is a property of the endpoint
rather than a branch inside a shared handler, so each can be tested directly. They differ in
inputs anyway: the self-service change requires the current password, the administrative one
does not.

**Enforce every authorization rule in the API, never in the MCP server.**
Satisfies `mcp-server` - *Act with the calling person's own privileges*. The MCP server is a
convenience layer: an assistant can be argued out of a policy check, and anyone can call the
API directly and bypass the server entirely. The server therefore carries the caller's own
authentication token and lets the API decide. This is also why Google sign-in returns a token
for the person rather than the server holding one shared credential - with a shared
credential the API could not tell an administrator from anyone else, and the
administrator-versus-self distinction would collapse.

**Match names without regard to case, and refuse ambiguity rather than choosing.**
Satisfies `user-management` - *Resolve the named account without regard to case* and
`user-signin` - *Refuse an absent or ambiguous matching account*. Because accounts created
outside signup are not normalised, a case-insensitive match can return more than one row.
Picking one would hand a caller power over an account that is not the one they named.

**Apply the field allowlist where the API's response is received, not in each tool.**
Satisfies `mcp-server` - *Disclose only the fields a tool needs*. One place decides what may
leave the HTTP boundary, so a tool cannot widen it and a field added to the API later does not
silently begin reaching the assistant. Filtering inside each tool was the alternative: it
re-implements the rule once per tool and fails open.

**Obtain the authentication token through a single function.**
Satisfies `mcp-server` - *Obtain a fresh authentication token once before failing*. One place
acquires the token, so the retry-once rule exists once rather than in every tool. That same
seam is where a cache or a self-signed token would later be substituted, which is why the
non-goals above cost nothing to defer.

**Rate-limit Google sign-in on the caller, not on an address.**
Satisfies `user-signin` - *Limit how often Google sign-in may be attempted*. The endpoint is
unauthenticated and the address is not known until Google answers, so there is nothing else to
key on at the moment the limit must be applied. The refusal must happen before the outbound
call, or the limit does not protect the thing it exists to protect.

**Keep these endpoints in their own module, and the MCP server outside the Django project.**
The existing views module covers the account lifecycle every caller uses; these four endpoints
exist for the MCP server. Separating them keeps each readable. The MCP server itself is a
top-level package with its own dependencies because it is a separate process that does not
import Django and must not join the Django test run.

## Risks / Trade-offs

**A password over 128 characters is refused where it was previously accepted.** → Signin does
not apply the strength rules, so an existing account whose password exceeds the new maximum
continues to authenticate normally. Only setting a password is affected. The refusal names the
limit, so anyone who hits it knows why.

**Signin does not bound the length of the password submitted to it.** → Deliberate, and it
costs nothing. The default hasher uses the password as an HMAC key, and HMAC reduces any key
longer than its block size to a fixed-size digest once, before the iterations begin - so
verifying a very long password costs the same as verifying a short one. Django also refuses an
oversized request body before a view sees it. Bounding signin would additionally lock out any
existing account whose password predates the new maximum, for no gain.

**Two outbound calls to Google per cold tool call, roughly a second before any work begins.**
→ Accepted for now. The MCP framework verifies the caller's Google token, and the API verifies
it again when issuing an authentication token. Neither is wrong; both are round trips. The
single token seam above is where this gets fixed when it is worth fixing, without touching any
tool.

**A successful self-service password change invalidates the very token the session is using.**
→ *Obtain a fresh authentication token once before failing* covers it: the next request is
refused, a fresh token is obtained, and the request is retried once. Without that rule a
caller who changes their own password finds every later tool call failing for no visible
reason.

**Google is a dependency of signing in.** → When Google cannot be reached, Google sign-in
fails; it is refused with the same response as any other token-side refusal. Email-and-password
signin is unaffected, so the API does not become unusable.

**The deployment is reached over plain HTTP.** → Authentication tokens and passwords traverse
the network unencrypted. Out of scope for this change, but every credential this change adds
is exposed to whatever the existing ones already are.
