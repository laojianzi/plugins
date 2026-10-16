# Nous Portal OAuth

An **experimental** OpenCode provider plugin for a Nous Portal account, with
independent device-code sign-in and automatic token renewal. It does not need
Hermes Agent or a running Hermes subscription proxy.

Package: `@magpie-community/opencode-nous-auth`. Provider id: `nous-portal`.
This is separate from magpie's **Nous Portal API-key preset** (`nous`): it does
not replace that preset, import its keys, or change its requests. It addresses
the OAuth portion of [magpie#392](https://github.com/yetone/magpie/issues/392),
not the independent API-key validation still discussed there.

**Verification status:** the offline tests exercise the public hooks and the
wire contract read from Hermes's source. A real Nous account, the vendor's
acceptance of this third-party use of its public client id, a running magpie,
and OpenCode have not been tested. Do not treat a passing offline test as proof
of subscription entitlement or a successful production login.

## Try the checkout

From this repository, with a magpie binary installed:

```sh
MAGPIE=/absolute/path/to/magpie sh scripts/try.sh nous
MAGPIE=/absolute/path/to/magpie sh scripts/try.sh nous login nous-portal
MAGPIE=/absolute/path/to/magpie sh scripts/try.sh nous provider test nous-portal
```

`try.sh` installs `packages/nous` under `.sandbox/nous` with isolated HOME,
USERPROFILE and XDG directories. It leaves the real gateway, agent configuration
and sign-ins alone. Do not use a portable Windows magpie executable here: it
ignores those home overrides. The last command sends real requests and can
consume the account's allowance.

Once this package has been reviewed and published, installation is:

```sh
magpie plugin add @magpie-community/opencode-nous-auth
magpie plugin login nous-portal
```

Or add `"@magpie-community/opencode-nous-auth"` to OpenCode's `plugin` array and
run `opencode auth login`. Publication and successful use in OpenCode are not
claimed by this change.

Approve the displayed device code in the Portal browser page. Finish login,
consent and any CAPTCHA yourself in that browser. The callback polls until
approval, denial or expiry; no local callback listener or browser automation
is started. An account's models and billing remain decisions of Nous Portal.
This plugin does not implement or promise a separate “Sign in with ChatGPT”
flow; any identity options on the Portal page are provided by the Portal.

## Protocol and ownership

The protocol constants and request shapes come from Hermes Agent's
[`auth_constants.py`](https://github.com/NousResearch/hermes-agent/blob/8b9ac5773ea07189f23aa9dfcdba1e59fd759c21/hermes_cli/auth_constants.py),
[`auth_device_flow.py`](https://github.com/NousResearch/hermes-agent/blob/8b9ac5773ea07189f23aa9dfcdba1e59fd759c21/hermes_cli/auth_device_flow.py),
[`auth_nous.py`](https://github.com/NousResearch/hermes-agent/blob/8b9ac5773ea07189f23aa9dfcdba1e59fd759c21/hermes_cli/auth_nous.py)
and its
[`NousPortalAdapter`](https://github.com/NousResearch/hermes-agent/blob/8b9ac5773ea07189f23aa9dfcdba1e59fd759c21/hermes_cli/proxy/adapters/nous_portal.py).

- Device authorization posts a form to
  `https://portal.nousresearch.com/api/oauth/device/code`, with public client
  `hermes-cli` and only `inference:invoke`. Token polling uses
  `/api/oauth/token` and the RFC 8628 device-code grant. There is no client
  secret. A separate registered magpie client has not been verified; vendor
  approval or a replacement registered client is a review prerequisite, not
  an invented identifier in this implementation.
- Renewal posts `grant_type=refresh_token` and `client_id=hermes-cli` to the
  same token endpoint. The refresh token goes in **`x-nous-refresh-token`**,
  not in the form or the inference request. The inference access token is a
  Bearer JWT with `inference:invoke`; there is no legacy agent-key exchange,
  anonymous-account mint, billing permission or automatic account import.
- Device polling respects the server's minimum interval (five seconds when
  absent) and adds five seconds for `slow_down`, as
  [RFC 8628 section 3.5](https://www.rfc-editor.org/rfc/rfc8628.html#section-3.5)
  specifies. This deliberately does not copy Hermes's one-second polling cap.
  Transport failures, rate limits and edge challenges back off, respecting
  `Retry-After`. A monotonic deadline begins at code issuance and ends no later
  than the server's expiry or thirty minutes locally. OAuth requests also
  have individual timeouts and never follow redirects.

### Where the sign-in is kept

The host owns its credential store; this package never reads or writes another
application's files. `auth.refresh` returns changed fields for magpie to save
with its account identity guard. OpenCode's per-request fallback saves through
`client.auth.set`, scoped by the host to the provider/account.

The stored shape is the standard `type: "oauth"`, `access`, `refresh`, `expires`.
`access` is the inference JWT. `expires` is epoch milliseconds, conservatively
the earlier of the token response's lifetime and the JWT's expiry when both
exist. `refresh` is a versioned JSON string holding the raw refresh token,
granted scope, token type and allowlisted inference base. Keeping metadata
inside this standard field also works with stores that discard extra fields.
**The whole refresh field is a secret**, not a configuration value to paste
into a report. No token is logged, and vendor error bodies/descriptions are
not copied into authentication errors. JWT decoding checks shape, scope and
expiry only; it does not verify a signature. The inference server does that.

Magpie's `auth.refreshLead` and the request fallback both renew two minutes
early. Concurrent renewals within one plugin instance share an exchange. A
rotated pair is kept in memory before validation or persistence; a failed save
is retried as a save rather than by spending its predecessor again. An
unusable successor is not sent to inference, but the host can retain its new
refresh token for recovery. A transient early-refresh outage can use the old
JWT only while it is still valid. Explicit dead-grant errors mark the sign-in
expired; an edge challenge, timeout, rate limit or server outage does not.

Magpie's scheduled refresh saves with the host's atomic identity check. The
request fallback re-reads the account before saving, retaining current
metadata and avoiding a new login it can observe. OpenCode's `auth.set` has no
compare-and-swap API: that fallback is an optimistic guard, **not an atomic
cross-process transaction**. Use one running host as owner of a token family.
Do not share this sign-in between processes or copy it into Hermes. Likewise,
do not copy Hermes's single-use refresh token into this plugin: independently
redeeming it can revoke Hermes's session. If an exchange succeeded remotely
but its response was lost, recovery may require a new login; no exactly-once
network guarantee is claimed. Memory-only successors cannot survive a crash
when their host save has failed.

### Requests and models

Requests use `@ai-sdk/openai-compatible`, not the Responses or Anthropic SDK.
Magpie owns client-protocol conversion. The plugin accepts only `/v1/models`,
`/v1/chat/completions`, `/v1/completions` and `/v1/embeddings` on the two known
production inference origins. An address in a token response cannot authorize
a new destination: only the exact HTTPS `/v1` bases on
`inference-api.nousresearch.com` and `welcome-api.nousresearch.com` are kept;
anything else is healed to the default production base. Redirects are refused.
There is no arbitrary-host or insecure-TLS override.

The loader returns a non-secret SDK placeholder. Each actual request obtains
the current account, replaces the caller's Authorization header, and removes
cookies, API keys, refresh-token headers and magpie-internal headers. A 401
cancels that response and permits one refresh/replay, using a newer bearer
already obtained by a concurrent caller where possible. It does not retry a
403, 429 or 5xx or reinterpret them as a revoked account. `X-Magpie-Sign-In`
reports `kept`, or `renewed` on a successful renewed request. Other response
status, headers and body are retained. JSON request bytes are buffered for
that one replay; response/SSE bytes are not buffered, parsed or rewritten.
Caller cancellation stops its request without abandoning another caller's
shared token renewal.

The model hook reads `/v1/models` with the account's Bearer token. It preserves
IDs verbatim, including `vendor/model`. A valid live list replaces the
bootstrap list, even if empty. An unreadable/malformed list is an error, not
an empty entitlement: magpie can keep its last successful list. Known model
metadata supplied by the host is retained; this plugin does not invent vision,
reasoning, prices or token limits. Zero cost/limit values are the host's
unknown-value defaults, not a claim of free usage or unlimited context.

`Hermes-4-70B` is a bootstrap entry from the official
[subscription-proxy examples](https://hermes-agent.nousresearch.com/docs/user-guide/features/subscription-proxy),
not proof that a particular account can use it. It satisfies the repository's
nonempty configuration contract before a live catalog is available.

The models hook receives only an auth **snapshot**, not `getAuth`. It therefore
never refreshes or writes that snapshot over a concurrent new login. Magpie
refreshes before calling it. In a host that does not refresh before model
listing, an expired snapshot fails rather than being persisted: refresh via a
normal request and retry the listing. This OpenCode lifecycle edge still needs
runtime validation. There is no fabricated usage/balance hook; Portal billing,
quota and additional protocol support are outside this change.

## Verification

The tests use `node:test`, fake HTTP replies, an injected monotonic clock and a
sandbox HOME. They do not reach a vendor or inspect real credentials. Fixtures
are synthetic protocol-shaped inputs derived from the linked Hermes code;
they are not captured successful production exchanges.

```sh
h=$(mktemp -d)
HOME="$h" TZ=UTC node --test packages/nous/index.test.mjs
HOME="$h" TZ=Pacific/Kiritimati node --test packages/nous/index.test.mjs
rm -rf "$h"

# Repository CI commands; run with Bun installed, from the repository root:
HOME=$(mktemp -d) bun test
bun scripts/check.mjs
```

Before calling this production-verified, confirm the public client's permitted
third-party use and exercise a real independent browser login, model listing,
nonstreaming and streaming/tool-call request, natural-expiry renewal, and a
restart after the rotated token is saved. Test cancellation and two independently
signed-in accounts in the sandbox as well. Do not manually redeem the same
refresh token from a second process to test rotation. The PR records exactly
which offline checks ran and which live/runtime checks remain unrun.
