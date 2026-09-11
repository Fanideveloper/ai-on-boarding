# mcp_server

An MCP server exposing the account-management endpoints of the Django project in
`sdd_django_demo/` as tools.

It is a separate process and imports nothing from that project - it calls the API over HTTP.
Install it into its own environment:

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest
```

Configuration, all read from the environment:

| Variable | Meaning |
| --- | --- |
| `DJANGO_API_BASE_URL` | Where the API lives, e.g. `http://127.0.0.1:8000` |
| `MCP_BASE_URL` | This server's own public address, where Google returns the caller after login |
| `GOOGLE_CLIENT_ID` | The Google OAuth client id this server authenticates callers with |
| `GOOGLE_CLIENT_SECRET` | Its client secret, used only to complete the Google login |

All four are required; the server refuses to start naming any that are missing.

The client id must also be listed in the Django project's `GOOGLE_OAUTH_CLIENT_IDS`, or the API
will refuse every token this server presents.

If the Django project sets `GOOGLE_ALLOWED_HD`, sign-in additionally requires the caller's
Google account to belong to that Workspace domain. Personal Google accounts carry no such
attestation and are refused; the API logs that case, because every token-side refusal shares
one response body and the two are otherwise indistinguishable from outside.

Behind a reverse proxy, set `DJANGO_NUM_PROXIES` on the Django side. Left unset, the sign-in
rate limit keys on the peer address, which is correct only when the API is reached directly.

## What this server stores

Worth knowing before deploying it, because none of it is this project's own code and it is easy
to miss. FastMCP's OAuth proxy, under the Google provider:

- mints its own JWTs for connected clients, signed with a key derived from `GOOGLE_CLIENT_SECRET`;
- persists each caller's upstream Google tokens to an encrypted file store, in a directory whose
  name is derived from that same secret;
- requests offline access, so what is persisted includes Google **refresh** tokens.

Treat that directory as a credential store: it belongs on the server's own disk, not in a
backup that travels, and rotating `GOOGLE_CLIENT_SECRET` invalidates everything in it.

