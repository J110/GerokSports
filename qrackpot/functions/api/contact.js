const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[c]));

const trim = (v) => (v == null ? '' : String(v).trim());

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export async function onRequestPost({ request, env }) {
  let data;
  try {
    data = await request.json();
  } catch {
    return json({ ok: false, error: 'Invalid JSON' }, 400);
  }

  const form = data && data.form;
  if (form !== 'partner' && form !== 'waitlist') {
    return json({ ok: false, error: 'Invalid form' }, 400);
  }

  const email = trim(data.email);
  if (!EMAIL_RE.test(email) || email.length > 254) {
    return json({ ok: false, error: 'Invalid email' }, 400);
  }

  const key = env.RESEND_API_KEY;
  if (!key) {
    return json({ ok: false, error: 'Server misconfigured' }, 500);
  }

  let subject;
  let text;
  let html;

  if (form === 'partner') {
    const name = trim(data.name);
    const company = trim(data.company);
    const tier = trim(data.tier);
    const message = trim(data.message);
    if (!name || !company || !tier || !message) {
      return json({ ok: false, error: 'Missing fields' }, 400);
    }
    subject = `[Qrackpot] Partner inquiry — ${name} / ${company} / ${tier}`;
    text =
      `Name: ${name}\n` +
      `Email: ${email}\n` +
      `Company: ${company}\n` +
      `Tier: ${tier}\n` +
      `Message: ${message}\n` +
      `---\n` +
      `Submitted from qrackpot.com`;
    html =
      `<p><strong>Name:</strong> ${esc(name)}</p>` +
      `<p><strong>Email:</strong> ${esc(email)}</p>` +
      `<p><strong>Company:</strong> ${esc(company)}</p>` +
      `<p><strong>Tier:</strong> ${esc(tier)}</p>` +
      `<p><strong>Message:</strong><br>${esc(message).replace(/\n/g, '<br>')}</p>` +
      `<hr><p><em>Submitted from qrackpot.com</em></p>`;
  } else {
    const sport = trim(data.sport);
    const country = trim(data.country);
    subject = `[Qrackpot] Waitlist signup — ${email}`;
    text =
      `Email: ${email}\n` +
      `Sport: ${sport || '—'}\n` +
      `Country: ${country || '—'}\n` +
      `---\n` +
      `Submitted from qrackpot.com`;
    html =
      `<p><strong>Email:</strong> ${esc(email)}</p>` +
      `<p><strong>Sport:</strong> ${esc(sport) || '—'}</p>` +
      `<p><strong>Country:</strong> ${esc(country) || '—'}</p>` +
      `<hr><p><em>Submitted from qrackpot.com</em></p>`;
  }

  try {
    const r = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${key}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: 'Qrackpot Forms <forms@qrackpot.com>',
        to: ['support@qrackpot.com'],
        reply_to: email,
        subject,
        text,
        html,
      }),
    });
    if (!r.ok) {
      return json({ ok: false, error: 'Send failed' }, 500);
    }
    return json({ ok: true });
  } catch {
    return json({ ok: false, error: 'Send failed' }, 500);
  }
}

export async function onRequest() {
  return new Response(
    JSON.stringify({ ok: false, error: 'Method not allowed' }),
    { status: 405, headers: { 'Content-Type': 'application/json', Allow: 'POST' } }
  );
}
