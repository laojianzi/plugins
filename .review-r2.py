# Verification branch only: apply a deterministic candidate to PR #163's head.
import hashlib
import json
import subprocess
import sys
from pathlib import Path

def blob(path):
    data = Path(path).read_bytes()
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()

def replace(s, old, new):
    assert s.count(old) == 1, old
    return s.replace(old, new)

mode = sys.argv[1]
if mode == 'tests':
    p = Path('packages/nous/index.test.mjs')
    assert blob(p) == '960cd0c16b4d7b8c289cc2f1fd3bc67de3d9cee7'
    p.write_text(p.read_text() + Path('.review-r2-tests.txt').read_text())
    assert blob(p) == 'e64700dd04b8047a51e9ed93b2fceb4401cbd648'
elif mode == 'fix':
    expected = {
        'packages/nous/index.mjs': 'd45ee8705f06142380af998e9a94dd75aa528712',
        'packages/nous/oauth.mjs': '009cc9ab94540d3328e4799991df098c3eae9a97',
        'packages/nous/README.md': 'bc2ea396d355cc94bef5befcd33467051077b123',
        'README.md': 'd7fef9c1ce079ae1d413ae7b2f9c867655ff90db',
        'registry.json': 'bf3be27d6b1a4110d55ab8433a9360464c64db79',
    }
    for path, sha in expected.items():
        assert blob(path) == sha, path
    p = Path('packages/nous/oauth.mjs'); s = p.read_text()
    s = replace(s, 'const GRANT = "urn:ietf:params:oauth:grant-type:device_code"', 'const FALLBACK_LIFETIME = 60 * 60 * 1000\nconst GRANT = "urn:ietf:params:oauth:grant-type:device_code"')
    s = replace(s, '''  const expiries = [
    positive(body?.expires_in) ? started + body.expires_in * 1000 : 0,
    typeof c.exp === "number" && Number.isFinite(c.exp) ? Math.max(1, c.exp * 1000) : 0,
  ].filter(positive)''', '''  // An absent lifetime needs a stable renewal schedule, not expires=1. An
  // explicitly expired or malformed bound must never be replaced by that default.
  const expiries = []
  if (body?.expires_in !== undefined) expiries.push(typeof body.expires_in === "number" ? started + body.expires_in * 1000 : NaN)
  if (c.exp !== undefined) expiries.push(typeof c.exp === "number" ? c.exp * 1000 : NaN)
  let expires = started + FALLBACK_LIFETIME
  if (expiries.length) expires = expiries.every(Number.isFinite) ? Math.max(1, Math.min(...expiries)) : 1''')
    s = replace(s, 'const result = { access, refresh: JSON.stringify(m), expires: expiries.length ? Math.min(...expiries) : 1 }', 'const result = { access, refresh: JSON.stringify(m), expires }')
    s = replace(s, '  const code = KNOWN.has(raw) ? raw : refreshing && !raw && [401, 403].includes(r.status) ? "invalid_grant" : "oauth_request_failed"', '  // A proxy or WAF can return 401/403 without the token endpoint seeing the\n  // grant. Only an explicit OAuth code is evidence that the grant is dead.\n  const code = KNOWN.has(raw) ? raw : "oauth_request_failed"')
    p.write_text(s)
    p = Path('packages/nous/index.mjs'); s = p.read_text()
    s = replace(s, '    const headers = new Headers(res.headers)\n    headers.set("X-Magpie-Sign-In"', '    const headers = new Headers(res.headers)\n    // fetch decodes the body; the upstream wire encoding and size no longer apply.\n    headers.delete("content-encoding")\n    headers.delete("content-length")\n    headers.set("X-Magpie-Sign-In"')
    p.write_text(s)
    p = Path('packages/nous/README.md'); s = p.read_text()
    start = s.index('## ChatGPT plan sharing\n')
    end = s.index('## Where the sign-in is kept\n')
    s = s[:start] + "For ChatGPT plan sharing, see [Nous Portal's documentation](https://portal.nousresearch.com/help/chatgpt-plan-sharing).\n\n" + s[end:]
    s = replace(s, '''For a plan-sharing check, confirm the connection and consent in Nous Portal
before sending an eligible inference request. Inspect ChatGPT's allowance and
Nous's account activity afterward; a successful request alone does not prove
which allowance paid for it.

''', '')
    s = replace(s, '''- Direct ChatGPT/Codex OAuth, ChatGPT/Portal billing and quota reporting,
  or daily check-in. Plan sharing is configured in Nous Portal.''', '- Direct ChatGPT/Codex OAuth, billing or quota reporting, or daily check-in.')
    s = replace(s, 'is secret**, even though it looks like JSON.\n', '''is secret**, even though it looks like JSON.

Expiry uses the earlier of the token response's lifetime and the JWT's `exp`.
If both are absent, renewal is scheduled one hour after the exchange, with
 the same two-minute lead. This is a local fallback, not a Nous lifetime
guarantee; a 401 can still trigger renewal sooner. Explicitly expired or
malformed lifetimes are not extended.
'''.replace('\n the same', '\nthe same'))
    s = replace(s, '''rotation may require signing in again. Explicit revoked-grant errors require
re-authentication, while temporary service or edge failures keep the sign-in.''', '''rotation may require signing in again. Only explicit `invalid_grant`,
`invalid_token` or `refresh_token_reused` errors mark the grant expired.
Other refresh refusals, including HTML or empty 401/403 responses, keep the
credentials and allow a later retry.''')
    s = replace(s, 'rewriting their content.\n', '''rewriting their content. The upstream `content-encoding` and `content-length`
headers are removed because fetch may already have decoded the body.
''')
    assert '## ChatGPT plan sharing' not in s and s.count('chatgpt-plan-sharing') == 1
    assert "Nous has not\nconfirmed whether independent clients" in s
    p.write_text(s)
    p = Path('README.md'); s = p.read_text()
    old = '| [nous](packages/nous) | Nous Portal OAuth, independent device sign-in and automatic renewal, with eligible ChatGPT plan sharing through Portal | `nous-portal` |'
    new = "| [nous](packages/nous) | Nous Portal models, with Nous Portal's device sign-in | `nous-portal` |"
    p.write_text(replace(s, old, new))
    p = Path('registry.json'); s = p.read_text(); before = json.loads(s)
    s = replace(s, 'Nous Portal OAuth device sign-in and token renewal, with eligible ChatGPT plan sharing configured in Portal. No Hermes Agent required.', "Nous Portal models, with Nous Portal's device sign-in.")
    s = replace(s, '通过设备码 OAuth 登录和自动续期接入 Nous Portal；可在 Portal 中关联符合条件的 ChatGPT 套餐共享推理用量，无需 Hermes Agent。', '通过 Nous Portal 自己的设备码登录使用 Nous Portal 模型。')
    after = json.loads(s)
    exclude = lambda v: [x for x in v['plugins'] if x['package'] != '@magpie-community/opencode-nous-auth']
    assert exclude(before) == exclude(after)
    assert len({x['package'] for x in after['plugins']}) == len(after['plugins'])
    p.write_text(s)
    for path, sha in {
        'packages/nous/index.mjs': '1c4e6f0d1809c215d7486313b79fe6ca3225dcdf',
        'packages/nous/oauth.mjs': 'e3f5303d5ab03b4bab7b172167c15961dbbb7819',
        'packages/nous/index.test.mjs': 'e64700dd04b8047a51e9ed93b2fceb4401cbd648',
    }.items():
        assert blob(path) == sha, path
    paths = sorted([*expected, 'packages/nous/index.test.mjs'])
    assert sorted(subprocess.check_output(['git', 'diff', '--name-only']).decode().splitlines()) == paths
    print(json.dumps({p: blob(p) for p in paths}, indent=2))
else:
    raise SystemExit('unknown mode')
