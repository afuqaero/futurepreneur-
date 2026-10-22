import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.SUPABASE_URL;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
const COMPONENTS = [
  ['strategy', 'Strategy & Model'], ['marketing', 'Marketing'], ['operations', 'Operations'],
  ['finance', 'Finance'], ['people', 'People'], ['systems', 'Systems'],
  ['legal', 'Legal & Risk'], ['digital', 'Digital'],
];

function json(body, status = 200, headers = {}) {
  const out = new Headers({ 'content-type': 'application/json; charset=utf-8' });
  for (const [key, value] of Object.entries(headers)) {
    if (Array.isArray(value)) value.forEach((item) => out.append(key, item));
    else out.set(key, value);
  }
  return new Response(JSON.stringify(body), { status, headers: out });
}

function cookies(request) {
  return Object.fromEntries((request.headers.get('cookie') || '').split(';')
    .map((part) => part.trim().split('='))
    .filter(([key, value]) => key && value)
    .map(([key, ...value]) => [key, value.join('=')]));
}

function cookie(name, value, maxAge = 60 * 60 * 24 * 7) {
  return `${name}=${encodeURIComponent(value)}; Max-Age=${maxAge}; Path=/; HttpOnly; SameSite=Lax; Secure`;
}

function clearCookie(name) {
  return cookie(name, '', 0);
}

async function sessionFromRequest(request) {
  const token = cookies(request).fp_access;
  if (!token) return null;
  const supabase = createClient(supabaseUrl, process.env.SUPABASE_ANON_KEY, {
    global: { headers: { Authorization: `Bearer ${decodeURIComponent(token)}` } },
  });
  const { data: { user } } = await supabase.auth.getUser();
  return user || null;
}

async function publicUser(user, db) {
  if (!user) return null;
  const { data: profile } = await db.from('profiles').select('name,role').eq('id', user.id).maybeSingle();
  return { id: user.id, email: user.email, name: profile?.name || user.user_metadata?.name || '', role: profile?.role || 'learner' };
}

async function progressFor(user, db) {
  if (!user) return null;
  const [{ data: profile }, { data: modules }, { data: diagnostics }, { data: plan }] = await Promise.all([
    db.from('profiles').select('*').eq('id', user.id).maybeSingle(),
    db.from('modules').select('id,component,title,position,status').eq('status', 'published').order('position'),
    db.from('diagnostic_results').select('overall,component_scores,created_at').eq('user_id', user.id).order('id', { ascending: false }).limit(1),
    db.from('plan_items').select('*').eq('user_id', user.id).order('done').order('id'),
  ]);
  const diagnostic = diagnostics?.[0] || null;
  const scores = diagnostic?.component_scores || {};
  const moduleRows = modules || [];
  const module = moduleRows[0] || { id: 'strategy', component: 'strategy', title: 'Business Strategy & Model', position: 1 };
  const planRows = plan || [];
  return {
    profile: profile || null,
    business_name: profile?.business_name || '', sector: profile?.sector || '', customer_type: profile?.customer_type || '',
    stage: profile?.stage || '', team_size: profile?.team_size || '', revenue_band: profile?.revenue_band || '',
    years: profile?.years || '', main_challenge: profile?.main_challenge || '',
    diagnostic: diagnostic ? { overall: diagnostic.overall, components: scores, created_at: diagnostic.created_at } : null,
    components: COMPONENTS.map(([id, name]) => ({ id, name, short: name, score: scores[id] ?? null, status: 'not_started' })),
    modules: moduleRows.map((m) => ({ id: m.id, component: m.component, title: m.title, lessons_done: 0, lessons_total: 0, passed: false, quiz_passed: false, scenario_passed: false, practical_passed: false })),
    module, focus_module: module, modules_total: moduleRows.length, modules_passed: 0,
    overall_percent: diagnostic?.overall || 0,
    mastery: { level: diagnostic ? 'Starting' : 'Not assessed', basis: diagnostic ? 'Based on your latest check-up.' : 'Complete your check-up to establish a baseline.' },
    next_steps: diagnostic ? [] : [{ title: 'Take the Business Check-Up', detail: 'See what to focus on first.', route: 'checkup' }],
    plan: planRows, plan_done: planRows.filter((p) => p.done).length,
    attempts: [], trend: [], settings: { quiz_pass: 80, scenario_pass: 70, rubric_min: 3 },
  };
}

async function coachReply(message, mode, user, db) {
  const { data: profile } = await db.from('profiles').select('business_name,sector,stage,main_challenge').eq('id', user.id).maybeSingle();
  const context = profile?.business_name
    ? `The business is ${profile.business_name} in ${profile.sector || 'an unspecified sector'}, at the ${profile.stage || 'current'} stage. Main challenge: ${profile.main_challenge || 'not provided'}.`
    : 'The learner has not completed their business profile yet.';
  const apiKey = process.env.DEEPSEEK_API_KEY || process.env.OPENAI_API_KEY;
  const baseUrl = (process.env.DEEPSEEK_BASE_URL || process.env.OPENAI_BASE_URL || 'https://api.deepseek.com').replace(/\/$/, '');
  const model = process.env.DEEPSEEK_MODEL || process.env.OPENAI_MODEL || 'deepseek-chat';
  if (!apiKey) {
    return `Demo coach mode: ${context}\n\nFor “${message}”, start by naming the customer, the specific problem, and one number you can check this week. Then choose one small experiment and review the result in seven days.`;
  }
  const response = await fetch(`${baseUrl}/chat/completions`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({
      model,
      temperature: 0.4,
      messages: [
        { role: 'system', content: `You are futurePreneur's practical business coach. Mode: ${mode}. Give concise, specific advice to a micro-business owner. Never invent verified scores. ${context}` },
        { role: 'user', content: message.slice(0, 4000) },
      ],
    }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error?.message || 'Coach provider failed.');
  return payload.choices?.[0]?.message?.content || 'I could not produce a response just now.';
}

function clientFromRequest(request) {
  const authorization = request.headers.get('authorization') || '';
  const client = createClient(supabaseUrl, process.env.SUPABASE_ANON_KEY, {
    global: { headers: authorization ? { Authorization: authorization } : {} },
  });
  return client;
}

function adminClient() {
  return createClient(supabaseUrl, serviceRoleKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
}

export default async function handler(request) {
  if (!supabaseUrl || !serviceRoleKey || !process.env.SUPABASE_ANON_KEY) {
    return json({ error: 'Supabase environment variables are not configured.' }, 503);
  }

  const url = new URL(request.url);
  if (url.pathname === '/api/health') {
    return json({ ok: true, service: 'futurepreneur-api' });
  }

  if (url.pathname === '/api/auth/login' && request.method === 'POST') {
    const body = await request.json();
    const supabase = createClient(supabaseUrl, process.env.SUPABASE_ANON_KEY);
    const { data, error } = await supabase.auth.signInWithPassword({
      email: String(body.email || '').trim().toLowerCase(),
      password: String(body.password || ''),
    });
    if (error || !data.session) return json({ error: 'Email or password is incorrect.', code: 'invalid_credentials' }, 401);
    const db = adminClient();
    return json({ user: await publicUser(data.user, db), progress: await progressFor(data.user, db) }, 200, {
      'set-cookie': [cookie('fp_access', data.session.access_token), cookie('fp_refresh', data.session.refresh_token)],
    });
  }

  if (url.pathname === '/api/auth/register' && request.method === 'POST') {
    const body = await request.json();
    const name = String(body.name || '').trim();
    const email = String(body.email || '').trim().toLowerCase();
    const password = String(body.password || '');
    if (name.length < 2 || password.length < 8 || !/^\S+@\S+\.\S+$/.test(email)) {
      return json({ error: 'Please enter a valid name, email and password of at least 8 characters.', code: 'invalid_input' }, 400);
    }
    const admin = adminClient();
    const { data, error } = await admin.auth.admin.createUser({ email, password, email_confirm: true, user_metadata: { name } });
    if (error) return json({ error: error.message.includes('already') ? 'An account with that email already exists.' : error.message, code: 'email_taken' }, 409);
    await admin.from('profiles').upsert({ id: data.user.id, name, role: 'learner' });
    const supabase = createClient(supabaseUrl, process.env.SUPABASE_ANON_KEY);
    const signedIn = await supabase.auth.signInWithPassword({ email, password });
    if (signedIn.error || !signedIn.data.session) return json({ error: 'Account created. Please sign in.', code: 'created' }, 201);
    return json({ user: await publicUser(signedIn.data.user, admin), progress: await progressFor(signedIn.data.user, admin) }, 201, {
      'set-cookie': [cookie('fp_access', signedIn.data.session.access_token), cookie('fp_refresh', signedIn.data.session.refresh_token)],
    });
  }

  if (url.pathname === '/api/auth/logout' && request.method === 'POST') {
    return json({ ok: true }, 200, { 'set-cookie': [clearCookie('fp_access'), clearCookie('fp_refresh')] });
  }

  // This endpoint is deliberately small until the Python route behavior has
  // been ported. It proves the Vercel/Supabase boundary without exposing the
  // service-role key to the browser.
  if (url.pathname === '/api/bootstrap' && request.method === 'GET') {
    const user = await sessionFromRequest(request);
    const db = adminClient();
    const apiUser = await publicUser(user, db);
    return json({
      user: apiUser,
      components: COMPONENTS.map(([id, name]) => ({ id, name, short: name, available: true })),
      settings: {},
      ai: { configured: Boolean(process.env.DEEPSEEK_API_KEY || process.env.OPENAI_API_KEY), mode: (process.env.DEEPSEEK_API_KEY || process.env.OPENAI_API_KEY) ? 'live' : 'demo' },
      progress: await progressFor(user, db),
    });
  }

  if (url.pathname === '/api/progress' && request.method === 'GET') {
    const user = await sessionFromRequest(request);
    if (!user) return json({ error: 'Authentication required.' }, 401);
    return json(await progressFor(user, adminClient()));
  }

  if (url.pathname === '/api/profile' && request.method === 'PUT') {
    const user = await sessionFromRequest(request);
    if (!user) return json({ error: 'Authentication required.' }, 401);
    const body = await request.json();
    const db = adminClient();
    const allowed = ['business_name', 'sector', 'customer_type', 'stage', 'team_size', 'revenue_band', 'years', 'main_challenge'];
    const patch = Object.fromEntries(allowed.filter((key) => key in body).map((key) => [key, String(body[key] || '').trim()]));
    const { error } = await db.from('profiles').update(patch).eq('id', user.id);
    if (error) return json({ error: error.message }, 400);
    return json({ ok: true, progress: await progressFor(user, db) });
  }

  if (url.pathname === '/api/coach' && request.method === 'POST') {
    const user = await sessionFromRequest(request);
    if (!user) return json({ error: 'Authentication required.' }, 401);
    const body = await request.json();
    const message = String(body.message || '').trim();
    if (!message) return json({ error: 'Send a message to the coach.', code: 'invalid_input' }, 400);
    const db = adminClient();
    let sessionId = body.session_id ? Number(body.session_id) : null;
    if (!sessionId) {
      const created = await db.from('coach_sessions').insert({ user_id: user.id, mode: body.mode || 'teach', title: message.slice(0, 90) }).select().single();
      if (created.error) return json({ error: created.error.message }, 400);
      sessionId = created.data.id;
    }
    await db.from('coach_messages').insert({ session_id: sessionId, role: 'user', content: message });
    const reply = await coachReply(message, body.mode || 'teach', user, db);
    await db.from('coach_messages').insert({ session_id: sessionId, role: 'assistant', content: reply });
    await db.from('coach_sessions').update({ updated_at: new Date().toISOString() }).eq('id', sessionId).eq('user_id', user.id);
    const { data: session } = await db.from('coach_sessions').select('id,mode,title,created_at,updated_at').eq('id', sessionId).single();
    return json({ reply, mode: (process.env.DEEPSEEK_API_KEY || process.env.OPENAI_API_KEY) ? 'live' : 'demo', session, session_id: sessionId });
  }

  if (url.pathname === '/api/coach/sessions' && request.method === 'GET') {
    const user = await sessionFromRequest(request);
    if (!user) return json({ error: 'Authentication required.' }, 401);
    const { data, error } = await adminClient().from('coach_sessions').select('id,mode,title,created_at,updated_at').eq('user_id', user.id).order('updated_at', { ascending: false });
    if (error) return json({ error: error.message }, 400);
    return json({ sessions: data || [] });
  }

  const sessionMatch = url.pathname.match(/^\/api\/coach\/sessions\/(\d+)$/);
  if (sessionMatch && request.method === 'GET') {
    const user = await sessionFromRequest(request);
    if (!user) return json({ error: 'Authentication required.' }, 401);
    const db = adminClient();
    const id = Number(sessionMatch[1]);
    const [{ data: session }, { data: messages }] = await Promise.all([
      db.from('coach_sessions').select('id,mode,title,created_at,updated_at').eq('id', id).eq('user_id', user.id).maybeSingle(),
      db.from('coach_messages').select('role,content,created_at').eq('session_id', id).order('id'),
    ]);
    if (!session) return json({ error: 'Conversation not found.' }, 404);
    return json({ session, messages: messages || [] });
  }

  return json({ error: 'Route not migrated yet.' }, 501);
}
