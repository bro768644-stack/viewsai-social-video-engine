/**
 * TRACKING WORKER — the behavioral capture layer (open pixels, click redirects, page events).
 *
 * Endpoints:
 *   GET  /o/<token>.gif     → records EMAIL_OPEN, returns a 1x1 transparent gif
 *   GET  /c/<slug>          → records EMAIL_CLICK/LINK_CLICK, 302 → destination
 *   POST /e                 → generic event beacon {event, email, asset, campaign, metadata, url}
 *   GET  /pixel.js          → drop-in page-view beacon for any site
 *   GET  /health
 *
 * Secrets (wrangler secret put):
 *   SUPABASE_URL, SUPABASE_SERVICE_KEY, TRACK_TOKEN
 *
 * Design notes:
 *   - Everything is fire-and-forget so pixels/redirects never block on the DB.
 *   - Opens are recorded but treated as WEAK signals (Apple MPP / scanners) — the scorer
 *     weights clicks, page views, downloads and replies far higher.
 *   - No cookies, no fingerprinting. Email + slug are the only identifiers.
 */

const GIF = Uint8Array.from(atob('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'), c => c.charCodeAt(0));

const WEIGHTS = {
  EMAIL_OPEN: 1, PAGE_VIEW: 3, WEBSITE_VISIT: 3, LINK_CLICK: 4, EMAIL_CLICK: 5,
  PDF_DOWNLOAD: 6, CALENDAR_VIEW: 8, FORM_SUBMIT: 10, REPLY: 10, CALL: 12,
};

function json(o, status = 200) {
  return new Response(JSON.stringify(o), {
    status, headers: { 'content-type': 'application/json', 'access-control-allow-origin': '*' },
  });
}

const cors = {
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'GET,POST,OPTIONS',
  'access-control-allow-headers': 'content-type,x-track-token',
};

async function sb(env, path, method, body) {
  const url = `${env.SUPABASE_URL}/rest/v1/${path}`;
  const r = await fetch(url, {
    method,
    headers: {
      apikey: env.SUPABASE_SERVICE_KEY,
      Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      'content-type': 'application/json',
      Prefer: 'return=minimal',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) console.log('supabase', r.status, (await r.text()).slice(0, 200));
  return r.ok;
}

/** Resolve a contact id from an email (create if missing) so events attach to identity. */
async function contactId(env, email) {
  if (!email) return null;
  const q = await fetch(
    `${env.SUPABASE_URL}/rest/v1/gtm_contacts?select=id&email=eq.${encodeURIComponent(email)}&limit=1`,
    { headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` } });
  if (q.ok) {
    const rows = await q.json();
    if (rows.length) return rows[0].id;
  }
  const domain = email.split('@')[1] || null;
  const ins = await fetch(`${env.SUPABASE_URL}/rest/v1/gtm_contacts`, {
    method: 'POST',
    headers: {
      apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}`,
      'content-type': 'application/json', Prefer: 'return=representation',
    },
    body: JSON.stringify({ email, company_domain: domain, source: 'tracking' }),
  });
  if (ins.ok) { const r = await ins.json(); return r[0]?.id || null; }
  return null;
}

async function record(env, ev) {
  const weight = ev.signal_weight || WEIGHTS[ev.event] || 2;
  const cid = ev.contact_id || await contactId(env, ev.email);
  await sb(env, 'contact_events', 'POST', [{
    contact_id: cid, email: ev.email || null, event: ev.event, source: ev.source || 'tracking',
    campaign: ev.campaign || null, asset: ev.asset || null, url: ev.url || null,
    signal_weight: weight, metadata: ev.metadata || {}, ip: ev.ip || null, user_agent: ev.user_agent || null,
  }]);
  return cid;
}

function pixel() {
  return new Response(GIF, {
    headers: { 'content-type': 'image/gif', 'cache-control': 'no-store, no-cache, must-revalidate, private' },
  });
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const path = url.pathname;

    if (req.method === 'OPTIONS') return new Response(null, { headers: cors });
    if (path === '/health') return json({ ok: true, service: 'tracking' });

    // ---------------- open pixel: /o/<token>.gif
    if (path.startsWith('/o/')) {
      const token = path.slice(3).replace(/\.gif$/, '');
      ctx.waitUntil((async () => {
        const q = await fetch(
          `${env.SUPABASE_URL}/rest/v1/open_pixels?select=id,email,outbound_id,campaign,opens,first_open_at&token=eq.${encodeURIComponent(token)}&limit=1`,
          { headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` } });
        if (!q.ok) return;
        const rows = await q.json();
        if (!rows.length) return;
        const px = rows[0];
        await sb(env, `open_pixels?id=eq.${px.id}`, 'PATCH',
          { opens: (px.opens || 0) + 1, last_open_at: new Date().toISOString() });
        await record(env, {
          email: px.email, event: 'EMAIL_OPEN', source: 'email', campaign: px.campaign,
          asset: token, ip: req.headers.get('cf-connecting-ip'),
          user_agent: req.headers.get('user-agent'),
          metadata: { outbound_id: px.outbound_id, likely_mpp: !px.first_open_at },
        });
      })());
      return pixel();
    }

    // ---------------- click redirect: /c/<slug>
    if (path.startsWith('/c/')) {
      const slug = path.slice(3);
      let dest = '/';
      try {
        const q = await fetch(
          `${env.SUPABASE_URL}/rest/v1/tracked_links?select=id,email,contact_id,destination,label,campaign,clicks,first_click_at&slug=eq.${encodeURIComponent(slug)}&limit=1`,
          { headers: { apikey: env.SUPABASE_SERVICE_KEY, Authorization: `Bearer ${env.SUPABASE_SERVICE_KEY}` } });
        if (q.ok) {
          const rows = await q.json();
          if (rows.length) {
            const l = rows[0];
            dest = l.destination;
            ctx.waitUntil((async () => {
              await sb(env, `tracked_links?id=eq.${l.id}`, 'PATCH', {
                clicks: (l.clicks || 0) + 1, last_click_at: new Date().toISOString(),
                ...(l.first_click_at ? {} : { first_click_at: new Date().toISOString() }),
              });
              await record(env, {
                contact_id: l.contact_id, email: l.email, event: 'EMAIL_CLICK', source: 'email',
                campaign: l.campaign, asset: l.label || slug, url: dest,
                ip: req.headers.get('cf-connecting-ip'), user_agent: req.headers.get('user-agent'),
                metadata: { slug },
              });
            })());
          }
        }
      } catch (e) { console.log('click', e.message); }
      return Response.redirect(dest, 302);
    }

    // ---------------- generic beacon: POST /e
    if (path === '/e' && req.method === 'POST') {
      let b = {};
      try { b = await req.json(); } catch { return json({ error: 'bad json' }, 400); }
      if (!b.event) return json({ error: 'event required' }, 400);
      const cid = await record(env, {
        email: b.email, contact_id: b.contact_id, event: b.event, source: b.source || 'web',
        campaign: b.campaign, asset: b.asset, url: b.url || req.headers.get('referer'),
        ip: req.headers.get('cf-connecting-ip'), user_agent: req.headers.get('user-agent'),
        metadata: b.metadata,
      });
      return json({ ok: true, contact_id: cid });
    }

    // ---------------- drop-in page beacon
    if (path === '/pixel.js') {
      const js = `
(function(){
  var d=document, s=d.currentScript;
  var base=s&&s.src?s.src.split('/pixel.js')[0]:'';
  var p=window.VIEWSAI_TRACK||{};
  function send(ev,extra){
    try{ navigator.sendBeacon(base+'/e', new Blob([JSON.stringify(Object.assign(
      {event:ev,email:p.email,campaign:p.campaign,asset:d.location.pathname,url:d.location.href},extra||{}))],
      {type:'application/json'})); }catch(e){}
  }
  send('PAGE_VIEW');
  d.addEventListener('visibilitychange',function(){ if(d.visibilityState==='hidden') send('PAGE_EXIT'); });
})();`;
      return new Response(js, { headers: { 'content-type': 'application/javascript', 'cache-control': 'public, max-age=3600' } });
    }

    return json({ error: 'not found' }, 404);
  },
};
