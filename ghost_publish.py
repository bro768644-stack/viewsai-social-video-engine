#!/usr/bin/env python3
"""Ghost Admin API publisher (JWT-signed). Publishes repurposed ViewsAI posts
and offer pages to Ghost via the Admin API."""
import base64, json, os, sys, time, urllib.request, hmac, hashlib

GHOST = "https://ghost.tryviewsai.com"   # direct HTTPS: the http://localhost:2368 301-redirects and drops POST bodies
ADMIN_KEY_ID = "6a8c7e1ad156ec000194087e"   # Ghost Admin API key (Zapier integration, api_keys.id)
ADMIN_SECRET = "41170bf037107ac2d9e00ed2d216d0e709680b077beea15e269825f25cc0df64"  # HEX — must be decoded

def b64url(data):
    if isinstance(data, str): data = data.encode()
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def jwt_token():
    header = b64url(json.dumps({"alg": "HS256", "kid": ADMIN_KEY_ID, "typ": "JWT"}))
    now = int(time.time())
    payload = b64url(json.dumps({"iat": now, "exp": now + 600, "aud": "/admin/"}))
    # Ghost admin secrets are hex strings -> decode to raw bytes for HMAC
    try:
        key_bytes = bytes.fromhex(ADMIN_SECRET)
    except ValueError:
        key_bytes = ADMIN_SECRET.encode()
    sig = hmac.new(key_bytes, f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{b64url(sig)}"

def api(method, path, body=None):
    req = urllib.request.Request(f"{GHOST}/ghost/api/admin{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Ghost {jwt_token()}", "Content-Type": "application/json",
                 "User-Agent": "ViewsAI-GhostPublisher/1.0 (+https://obrienhq.com)"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            raw = r.read()
            return json.loads(raw) if raw else {"status": r.status}
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": e.read().decode()[:300]}

def slugify(s):
    return "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")[:80]

def publish_post(title, html, tags=None, featured=False):
    tags_list = [{"name": t.strip()} for t in (tags or "").split(",") if t.strip()]
    body = {"posts": [{"title": title, "html": html, "status": "published",
                        "featured": featured,
                        "tags": tags_list}]}
    return api("POST", "/posts/?source=html", body)

def set_site(settings):
    return api("PUT", "/settings/", {"settings": settings})

def upload_image(src_path):
    import uuid as _uuid
    boundary = "----ViewsAI" + _uuid.uuid4().hex
    with open(src_path, 'rb') as f:
        file_bytes = f.read()
    fname = os.path.basename(src_path)
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'.encode()
    body += b"Content-Type: image/png\r\n\r\n"
    body += file_bytes + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{GHOST}/ghost/api/admin/images/upload/", method="POST",
        data=body, headers={"Authorization": f"Ghost {jwt_token()}",
                            "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": e.read().decode()[:200]}

def publish_page(title, html, tags=None):
    body = {"pages": [{"title": title, "html": html, "status": "published",
                       "tags": [{"name": t.strip()} for t in (tags or "").split(",") if t.strip()]}]}
    return api("POST", "/pages/?source=html", body)

def md_to_html(md):
    """Very small markdown->HTML for our generated post format."""
    import html
    out, in_list = [], False
    for ln in md.splitlines():
        s = ln.rstrip()
        if s.startswith('# '): out.append(f"<h1>{html.escape(s[2:])}</h1>")
        elif s.startswith('## '): out.append(f"<h2>{html.escape(s[3:])}</h2>")
        elif s.startswith('### '): out.append(f"<h3>{html.escape(s[4:])}</h3>")
        elif s.startswith('- '):
            if not in_list: out.append("<ul>"); in_list = True
            out.append(f"<li>{html.escape(s[2:])}</li>")
        elif s.strip() == '':
            if in_list: out.append("</ul>"); in_list = False
        else:
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<p>{html.escape(s)}</p>")
    if in_list: out.append("</ul>")
    return "\n".join(out)

if __name__ == "__main__":
    # test: create one published post
    r = publish_post("ViewsAI Test Post", "<h1>Hello</h1><p>Ghost Admin API works.</p>", tags="Test")
    print(json.dumps(r, indent=2)[:500] if 'error' not in r else r)
