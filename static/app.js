/* futurePreneur — frontend application (vanilla JS, hash router, server-backed) */
'use strict';

/* ------------------------------------------------------------------ utils */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const state = {
  user: null,
  progress: null,
  components: [],
  settings: {},
  ai: { configured: false, mode: 'demo' },
  authMode: 'login',
  authError: '',
  authBusy: false,
  editProfile: false,
  checkupResult: null,
  runner: null,
  assessmentResult: null,
  practicalForm: false,
  moduleData: null,
  coach: { mode: 'teach', messages: [], busy: false },
  admin: { tab: 'learners', qkind: 'all', editing: null, showForm: false, lesson: 'l1', content: null, moduleId: null, template: null, newModule: false, newTemplate: false, preview: false },
};
let seq = 0;
let lastRoute = '';

function begin() { return ++seq; }

function esc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return '—';
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function fmtDateTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return '—';
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) + ', ' +
    d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

function initials(name) {
  return String(name || '?').trim().split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase();
}

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

function masteryClass(level) {
  return String(level || 'Not assessed').toLowerCase().replace(/\s+/g, '-');
}

function compName(id) {
  const c = state.components.find(x => x.id === id);
  return c ? c.name : id;
}

function compMeta(id) {
  return state.components.find(x => x.id === id) || { name: id, short: id, available: false };
}

const DIAG_RECS = {
  strategy: 'Start with the Business Strategy & Model module: define one primary customer, write your value proposition, and calculate contribution per sale.',
  marketing: 'Write down your single best customer group and the one offer you want them to buy. Then track where enquiries come from for two weeks.',
  operations: 'Map your busiest process on one page, mark the two points where mistakes happen, and add a simple check at each point.',
  finance: 'Separate fixed and variable costs, then calculate your break-even sales. Review cash in and cash out weekly.',
  people: 'Clarify each role in one page: what good looks like, what decisions they can make, and who checks quality.',
  systems: 'Turn your most repeated task into a one-page checklist and test it with someone else doing the task.',
  legal: 'List the licences, contracts and insurance your business depends on, and note the renewal dates in one place.',
  digital: 'Choose one digital channel, measure cost per order and repeat orders for 30 days, and drop anything you cannot measure.',
};

/* Owner-facing grouping of the eight diagnostic components. Scores are
   diagnostic baselines only; verified badges come from passed modules. */
const ASPECTS = [
  { id: 'marketing', label: 'Marketing', components: ['marketing'], blurb: 'Customers, offer, channels and repeat sales' },
  { id: 'finance', label: 'Finance', components: ['finance'], blurb: 'Cash, margins and pricing decisions' },
  { id: 'operations', label: 'Operations', components: ['operations'], blurb: 'Quality, capacity and reliable delivery' },
  { id: 'management', label: 'Management', components: ['strategy', 'systems'], blurb: 'Direction, priorities and how work gets done' },
  { id: 'people-growth', label: 'People & Growth', components: ['people', 'digital'], blurb: 'Team, digital tools and expansion' },
];

function aspectSummary(progress, aspect) {
  const comps = aspect.components.map((id) => progress.components.find((c) => c.id === id)).filter(Boolean);
  const scored = comps.filter((c) => typeof c.score === 'number');
  const score = scored.length ? Math.round(scored.reduce((sum, c) => sum + c.score, 0) / scored.length) : null;
  const verified = comps.filter((c) => c.status === 'passed').length;
  return { score, verified, total: comps.length };
}

function cookieValue(name) {
  const match = document.cookie.split('; ').find((row) => row.startsWith(name + '='));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : '';
}

async function readBody(res) {
  const type = res.headers.get('content-type') || '';
  return type.includes('application/json') ? res.json() : res.text();
}

async function api(path, options = {}) {
  const opts = Object.assign({ credentials: 'same-origin' }, options);
  const method = (opts.method || 'GET').toUpperCase();
  opts.headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});

  // Every state-changing request needs the double-submit CSRF token.
  if (method !== 'GET' && !cookieValue('br_csrf')) {
    await fetch('/api/bootstrap', { credentials: 'same-origin' });
  }
  if (method !== 'GET') opts.headers['X-CSRF-Token'] = cookieValue('br_csrf');

  let res = await fetch(path, opts);
  let data = await readBody(res);

  if (res.status === 403 && data && data.code === 'csrf_invalid') {
    await fetch('/api/bootstrap', { credentials: 'same-origin' });
    opts.headers['X-CSRF-Token'] = cookieValue('br_csrf');
    res = await fetch(path, opts);
    data = await readBody(res);
  }

  if (!res.ok) {
    if (res.status === 401 && state.user) {
      state.user = null;
      state.progress = null;
      renderAuth();
    }
    throw new Error((data && data.error) || 'Request failed.');
  }
  return data;
}

function toast(message, kind = '') {
  const wrap = $('#toast');
  if (!wrap) return;
  const el = document.createElement('div');
  el.className = 'toast-item ' + kind;
  el.textContent = message;
  wrap.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .2s'; }, 3200);
  setTimeout(() => el.remove(), 3500);
}

/* ------------------------------------------------------------------ icons */
const ICONS = {
  dashboard: '<rect x="3" y="3" width="7" height="8" rx="1.6"/><rect x="14" y="3" width="7" height="5" rx="1.6"/><rect x="3" y="15" width="7" height="6" rx="1.6"/><rect x="14" y="12" width="7" height="9" rx="1.6"/>',
  checkup: '<path d="M9 4h6"/><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 12l2 2 4-4"/>',
  learn: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
  coach: '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9.9 9.9 0 0 1-3.9-.8L3 21l1.9-4.9A8.4 8.4 0 1 1 21 11.5z"/><path d="M8.5 11.5h.01M12 11.5h.01M15.5 11.5h.01"/>',
  test: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.4"/>',
  progress: '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>',
  admin: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3"/><circle cx="4" cy="12" r="2"/><circle cx="12" cy="10" r="2"/><circle cx="20" cy="14" r="2"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  right: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  left: '<path d="M19 12H5M11 18l-6-6 6-6"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  lock: '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  spark: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  send: '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4z"/>',
  close: '<path d="M18 6 6 18M6 6l12 12"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  briefcase: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M3 12h18"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4M16 3v4M3 11h18"/>',
  chevron: '<path d="M6 9l6 6 6-6"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
  arrowup: '<path d="M12 19V5M5 12l7-7 7 7"/>',
};

function icon(name, size = 18) {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;
}

function ring(pct, size = 118, stroke = 9, label = 'complete', light = false) {
  const p = Math.max(0, Math.min(100, Number(pct) || 0));
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - p / 100);
  return `<div class="ring ${light ? 'light' : ''}" style="width:${size}px;height:${size}px">
    <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
      <circle class="ring-track" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="${stroke}"/>
      <circle class="ring-val" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="${stroke}"
        stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}"/>
    </svg>
    <div class="ring-txt"><b>${p}%</b><span>${esc(label)}</span></div>
  </div>`;
}

function bar(pct, cls = '') {
  return `<div class="bar ${cls}"><span style="width:${Math.max(0, Math.min(100, Number(pct) || 0))}%"></span></div>`;
}

function pill(level) {
  return `<span class="mastery-pill ${masteryClass(level)}">${esc(level)}</span>`;
}

function loadingHTML() {
  return `<div class="loading"><span class="spinner"></span> Loading your workspace…</div>`;
}

function errorHTML(message) {
  return `<div class="card card-pad"><div class="empty"><div class="icon">${icon('alert', 22)}</div>
    <p class="strong">We could not load this page.</p><p class="small muted">${esc(message)}</p>
    <button class="btn btn-outline btn-sm" data-action="reload">Try again</button></div></div>`;
}

function mount(html, mySeq) {
  if (mySeq !== undefined && mySeq !== seq) return false;
  const el = $('#view');
  if (!el) return false;
  el.innerHTML = html;
  return true;
}

/* ------------------------------------------------------------------ auth */
function renderAuth() {
  document.title = 'Sign in · futurePreneur';
  const isLogin = state.authMode === 'login';
  const err = state.authError ? `<div class="auth-error">${esc(state.authError)}</div>` : '';
  $('#app').innerHTML = `
  <div class="auth">
    <section class="auth-art">
      <div class="auth-brand">
        <div class="brand-mark">f</div>
        <div class="auth-brand-text">
          <div class="brand-name">futurePreneur</div>
          <div class="brand-sub" style="color:#7FA2C4">Business readiness platform</div>
        </div>
      </div>
      <div class="auth-copy">
        <div class="eyebrow" style="color:#62DED2">Built for owners, not accountants</div>
        <h1>Turn experience into a business that <em>runs on purpose.</em></h1>
        <p class="lead">Assess your business, learn the structure behind it, and test what you know — one practical step at a time.</p>
        <ul class="auth-flow">
          <li><span class="num">01</span> Business Check-Up across eight core areas</li>
          <li><span class="num">02</span> Practical lessons built for micro and small businesses</li>
          <li><span class="num">03</span> A coach that helps you think it through</li>
          <li><span class="num">04</span> Scored assessments and a verified progress record</li>
        </ul>
      </div>
      <div class="auth-foot">4 of 8 modules live · built for micro-business owners.</div>
    </section>
    <section class="auth-panel">
      <div class="auth-card">
        <div class="auth-mobile-brand">
          <div class="brand-mark">f</div>
          <div style="margin-left:10px"><div class="brand-name" style="color:#0F2A66;font-size:20px">futurePreneur</div>
          <div class="brand-sub">Business readiness</div></div>
        </div>
        <h2>${isLogin ? 'Welcome back' : 'Create your account'}</h2>
        <p class="sub">${isLogin ? 'Sign in to continue your business development plan.' : 'Start with a check-up, then work through the core module.'}</p>
        <div class="auth-toggle">
          <button type="button" class="${isLogin ? 'on' : ''}" data-action="auth-mode" data-mode="login">Sign in</button>
          <button type="button" class="${!isLogin ? 'on' : ''}" data-action="auth-mode" data-mode="register">Create account</button>
        </div>
        ${err}
        <form data-form="${isLogin ? 'login' : 'register'}" autocomplete="on">
          ${isLogin ? '' : `<div class="field"><label for="name">Full name</label>
            <input class="input" id="name" name="name" placeholder="Aina Rahman" autocomplete="name" required></div>`}
          <div class="field"><label for="email">Email</label>
            <input class="input" id="email" name="email" type="email" placeholder="you@business.com" autocomplete="email" required></div>
          <div class="field"><label for="password">Password</label>
            <input class="input" id="password" name="password" type="password" placeholder="${isLogin ? 'Your password' : 'At least 8 characters'}" autocomplete="${isLogin ? 'current-password' : 'new-password'}" required minlength="${isLogin ? '1' : '8'}"></div>
          <button class="btn btn-primary btn-block btn-lg" type="submit">${isLogin ? 'Sign in' : 'Create account'} ${icon('right', 15)}</button>
        </form>
        <div class="demo-box">
          <div class="row-between" style="margin-bottom:7px">
            <span class="tiny strong">Demo accounts</span>
            <span class="tiny muted">Pre-loaded with realistic data</span>
          </div>
          <div class="row wrap" style="gap:6px">
            <button type="button" class="demo-btn" data-action="demo-login" data-email="aina@futurepreneur.app" data-password="Demo1234!">Learner · Aina</button>
            <button type="button" class="demo-btn" data-action="demo-login" data-email="admin@futurepreneur.app" data-password="Admin1234!">Admin</button>
            <span class="tiny muted" style="margin-left:auto">aina@futurepreneur.app / Demo1234!</span>
          </div>
        </div>
        <p class="tiny muted" style="margin-top:18px">Progress is stored on the server. The AI coach runs in clearly labelled demo mode until an API key is configured.</p>
      </div>
    </section>
  </div>`;
}

async function doLogin(email, password) {
  state.authBusy = true;
  state.authError = '';
  try {
    const data = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
    state.user = data.user;
    state.progress = data.progress;
    state.authError = '';
    state.authMode = 'login';
    const target = data.user.role === 'admin' ? '#/admin' : '#/dashboard';
    if (location.hash === target) router(); else location.hash = target;
  } catch (err) {
    state.authError = err.message;
    renderAuth();
  } finally {
    state.authBusy = false;
  }
}

async function doRegister(form) {
  state.authError = '';
  const payload = {
    name: form.elements.name.value.trim(),
    email: form.elements.email.value.trim(),
    password: form.elements.password.value,
  };
  try {
    const data = await api('/api/auth/register', { method: 'POST', body: JSON.stringify(payload) });
    state.user = data.user;
    state.progress = data.progress;
    location.hash = '#/checkup';
    router();
  } catch (err) {
    state.authError = err.message;
    renderAuth();
  }
}

/* ------------------------------------------------------------------ shell */
const NAV = [
  { id: 'dashboard', label: 'Dashboard', href: '#/dashboard', icon: 'dashboard' },
  { id: 'checkup', label: 'Business Check-Up', href: '#/checkup', icon: 'checkup' },
  { id: 'learn', label: 'Learn & Improve', href: '#/learn', icon: 'learn' },
  { id: 'coach', label: 'AI Business Coach', href: '#/coach', icon: 'coach' },
  { id: 'test', label: 'Test Your Skills', href: '#/test', icon: 'test' },
  { id: 'progress', label: 'My Business Progress', href: '#/progress', icon: 'progress' },
];

const COMP_STYLE = {
  strategy: { emoji: '🧭', short: 'Know what you sell, to whom, and why it wins.' },
  marketing: { emoji: '📣', short: 'Get found, get chosen, get paid.' },
  operations: { emoji: '⚙️', short: 'Same good result every time — without you hovering.' },
  finance: { emoji: '💸', short: 'Know your numbers. Keep more of what you earn.' },
  people: { emoji: '🫶', short: 'Hire right, delegate well, keep good people.' },
  systems: { emoji: '🧩', short: 'Write it down once. Stop repeating yourself.' },
  legal: { emoji: '🛡️', short: 'Cover the basics before they bite.' },
  digital: { emoji: '🚀', short: 'Tools that save hours, not more apps.' },
};
const compStyle = (id) => COMP_STYLE[id] || { emoji: '✨', short: 'Practical skills for your business.' };


function renderShell(active) {
  const p = state.progress;
  const business = p && p.profile ? p.profile.business_name : 'Your business';
  const level = state.user && state.user.role === 'admin' ? 'Admin' : (p && p.mastery ? p.mastery.level : 'Not assessed');
  const adminLink = state.user.role === 'admin'
    ? `<div class="nav-label">Administration</div><div class="nav"><a href="#/admin" data-nav="admin" class="${active === 'admin' ? 'active' : ''}">${icon('admin')}<span>Manage platform</span></a></div>` : '';
  $('#app').innerHTML = `
  <div class="app">
    <aside class="sidebar" id="sidebar">
      <a class="brand" href="#/dashboard">
        <div class="brand-mark">f</div>
        <div class="brand-text"><span class="brand-name">futurePreneur</span><span class="brand-sub">Business readiness</span></div>
      </a>
      <div class="nav-label">Workspace</div>
      <nav class="nav">
        ${NAV.map(n => `<a href="${n.href}" data-nav="${n.id}" class="${active === n.id ? 'active' : ''}">
          ${icon(n.icon)}<span>${n.label}</span>${n.id === 'test' && p && p.module.passed ? '<span class="nav-count">✓</span>' : ''}
        </a>`).join('')}
      </nav>
      ${adminLink}
      <div class="sidebar-foot">
        <div class="side-user">
          <div class="avatar">${esc(initials(state.user.name))}</div>
          <div class="who"><b>${esc(state.user.name)}</b><span>${esc(business)}</span></div>
          <button class="icon-btn" type="button" data-action="logout" title="Sign out" aria-label="Sign out">${icon('logout', 16)}</button>
        </div>
        <div class="side-note">${icon('shield', 12)} <span>Your progress is saved to this account.</span></div>
      </div>
    </aside>
    <div class="backdrop" id="backdrop" data-action="close-menu"></div>
    <div class="main">
      <header class="topbar">
        <button class="menu-btn" type="button" data-action="open-menu" aria-label="Open navigation">${icon('menu', 19)}</button>
        <div class="crumb"><span class="crumb-root">Workspace <span style="color:#B4C2CF">/</span> </span><b>${esc(NAV.find(n => n.id === active) ? NAV.find(n => n.id === active).label : active === 'admin' ? 'Admin' : 'Dashboard')}</b></div>
        <div class="spacer"></div>
        <span class="top-chip hide-sm">${icon('briefcase', 13)} ${esc(business)}</span>
        <span class="top-chip ${level === 'Optimising' ? 'gold' : ''}"><span class="dot"></span>${esc(level)}</span>
      </header>
      <main id="view" class="view"></main>
    </div>
  </div>
  <div id="toast"></div>`;
}

function setActiveNav(active) {
  $$('.sidebar .nav a[data-nav]').forEach(a => a.classList.toggle('active', a.dataset.nav === active));
}

/* ------------------------------------------------------------------ router */
async function router() {
  if (!state.user) { renderAuth(); return; }
  const raw = location.hash.replace(/^#\/?/, '') || 'dashboard';
  const parts = raw.split('/').filter(Boolean);
  const root = parts[0] || 'dashboard';
  const sub = parts[1] || '';
  const navKey = root === 'module' ? 'learn' : root;
  const titles = {
    dashboard: 'Dashboard',
    checkup: 'Business Check-Up',
    learn: sub === 'strategy' ? 'Business Strategy & Model' : 'Learn & Improve',
    coach: 'AI Business Coach',
    test: sub === 'practical' ? 'Practical assignment' : sub === 'quiz' ? 'Knowledge quiz' : sub === 'scenario' ? 'Scenario test' : 'Test Your Skills',
    progress: 'My Business Progress',
    admin: 'Admin',
  };
  document.title = (titles[root] || 'Workspace') + ' · futurePreneur';
  renderShell(['dashboard', 'checkup', 'learn', 'coach', 'test', 'progress', 'admin'].includes(navKey) ? navKey : 'dashboard');
  const my = begin();
  if (raw !== lastRoute) {
    state.assessmentResult = (root === 'test' && sub) ? state.assessmentResult : null;
    lastRoute = raw;
  }
  const view = $('#view');
  if (view) view.innerHTML = loadingHTML();
  window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
  try {
    if (root === 'dashboard') await viewDashboard(my);
    else if (root === 'checkup') await viewCheckup(my);
    else if (root === 'learn' && sub) await viewModule(my, sub);
    else if (root === 'learn') await viewLearn(my);
    else if (root === 'coach') renderCoach(my);
    else if (root === 'test') await viewTest(my, sub);
    else if (root === 'progress') await viewProgress(my);
    else if (root === 'admin') await viewAdmin(my, sub);
    else notFound(my);
  } catch (err) {
    mount(errorHTML(err.message), my);
  }
}

function notFound(my) {
  mount(`<div class="card card-pad"><div class="empty"><div class="icon">${icon('info', 22)}</div>
    <p class="strong">That page does not exist.</p><p class="small muted">Return to your dashboard to continue.</p>
    <a class="btn btn-primary btn-sm" href="#/dashboard">Go to dashboard</a></div></div>`, my);
}

/* ------------------------------------------------------------------ dashboard */
async function viewDashboard(my) {
  const progress = await api('/api/progress');
  if (my !== seq) return;
  state.progress = progress;
  const p = progress;
  const mod = p.module;
  const next = p.next_steps[0] || { title: 'Keep your weekly review going', detail: 'One action this week is enough.', route: 'progress' };
  const nextLabel = { checkup: 'Start check-up', module: 'Open module', test: 'Take a test', progress: 'See my plan' }[next.route] || 'Continue';
  const firstName = state.user.name.split(' ')[0];

  const steps = [
    { id: 'checkup', label: 'Check-Up', sub: p.diagnostic ? 'Done' : 'Start here', href: '#/checkup', done: !!p.diagnostic },
    { id: 'learn', label: 'Learn', sub: `${mod.lessons_done}/${mod.lessons_total} lessons`, href: `#/learn/${mod.id}`, done: mod.lessons_done === mod.lessons_total },
    { id: 'coach', label: 'Coach', sub: 'Ask anything', href: '#/coach', done: false },
    { id: 'test', label: 'Test', sub: `${[mod.quiz_passed, mod.scenario_passed, mod.practical_passed].filter(Boolean).length}/3 passed`, href: '#/test', done: mod.passed },
    { id: 'progress', label: 'Progress', sub: p.mastery.level, href: '#/progress', done: mod.passed },
  ];
  let currentAssigned = false;
  const journey = steps.map(s => {
    let cls = s.done ? 'done' : '';
    if (!s.done && !currentAssigned && !mod.passed) { cls = 'current'; currentAssigned = true; }
    return `<a class="jstep ${cls}" href="${s.href}">
      <span class="jdot">${s.done ? icon('check', 13) : ''}</span>
      <span class="jt"><b>${s.label}</b><span>${s.sub}</span></span>
    </a>`;
  }).join('');

  mount(`
  <section class="hero">
    <div class="hero-copy">
      <span class="hero-pill">👋 Hey ${esc(firstName)}</span>
      <h1>Your business.<br><em>Levelled up.</em></h1>
      <p>${p.diagnostic ? 'One small step today beats a perfect plan next month.' : 'Take the 5-minute check-up. We\'ll show you what to fix first.'}</p>
      <div class="hero-actions">
        <a class="btn btn-primary btn-lg" href="${next.route === 'module' ? `#/learn/${mod.id}` : `#/${next.route}`}">${nextLabel} ${icon('right', 15)}</a>
        <a class="hero-link" href="#/coach">${icon('coach', 14)} Ask the coach</a>
      </div>
    </div>
    <div class="hero-art">
      <img src="/static/img/hero-collage.svg" alt="Business progress illustration" width="390" height="337">
      <div class="hero-sticker"><b>${p.overall_percent}%</b><span>${esc(p.mastery.level)} · ready</span></div>
    </div>
  </section>

  <div class="section"><div class="journey">${journey}</div></div>

  <div class="section grid grid-3">
    <div class="stat"><div class="k">🔥 Readiness</div><div class="v">${p.overall_percent}<small>%</small></div><div class="s">Across 8 business areas</div></div>
    <div class="stat"><div class="k">🎯 Mastery</div><div class="v" style="font-size:23px;margin-top:10px">${esc(p.mastery.level)}</div><div class="s">Verified results only</div></div>
    <div class="stat"><div class="k">✅ Action plan</div><div class="v">${p.plan_done}<small> / ${p.plan.length}</small></div><div class="s">Steps completed</div></div>
  </div>

  <div class="section split">
    <div class="card card-pad">
      <div class="card-head"><div><h2>Next up</h2><p>Small moves, in order.</p></div><a class="link-arrow" href="#/progress">Full plan ${icon('right', 13)}</a></div>
      ${p.next_steps.slice(0, 3).map((s, i) => `
        <a class="action-item" href="#/${s.route}">
          <span class="num">${String(i + 1).padStart(2, '0')}</span>
          <span class="txt"><b>${esc(s.title)}</b><span>${esc(s.detail)}</span></span>
          <span class="go">${icon('right', 15)}</span>
        </a>`).join('')}
      ${p.next_steps.length === 0 ? `<div class="empty">All required steps are complete. Keep your weekly review going.</div>` : ''}
    </div>

    <div>
      <div class="card card-pad">
        <div class="card-head" style="margin-bottom:4px"><div><h2>Your 8 areas</h2></div><a class="link-arrow" href="#/checkup">Check-up ${icon('right', 13)}</a></div>
        ${p.components.map((c, i) => `
          <div class="comp-row">
            <span class="swatch">${String(i + 1).padStart(2, '0')}</span>
            <span class="nm">${esc(c.name)}</span>
            ${c.score != null ? bar(c.score) : `<span class="tiny muted" style="width:84px;text-align:center">Not assessed</span>`}
            <span class="sc">${c.score != null ? c.score + '%' : '—'}</span>
          </div>`).join('')}
      </div>

      <div class="coach-mini" style="margin-top:14px">
        <img src="/static/img/coach-bubbles.svg" alt="">
        <h3>Stuck on something?</h3>
        <p>Tell the coach what's happening. Get a plan, not a lecture.</p>
        <a class="btn btn-teal btn-sm" href="#/coach">Ask now ${icon('right', 12)}</a>
        ${state.ai.configured ? '' : `<div class="tiny" style="color:#C9D4FF;margin-top:9px">Demo mode · add an API key for live answers</div>`}
      </div>
    </div>
  </div>`, my);
}

/* ------------------------------------------------------------------ checkup */
function profileForm(profile) {
  const p = profile || {};
  const opt = (val, current) => `<option value="${esc(val)}" ${val === current ? 'selected' : ''}>${esc(val)}</option>`;
  return `<form data-form="profile">
    <div class="field-row">
      <div class="field"><label for="business_name">Business name</label>
        <input class="input" id="business_name" name="business_name" value="${esc(p.business_name || '')}" placeholder="Aina's Kitchen" required></div>
      <div class="field"><label for="sector">Sector</label>
        <select class="select" id="sector" name="sector" required>
          ${['Food & beverage', 'Online retail', 'Services', 'Retail shop', 'Manufacturing', 'Education & training', 'Other'].map(v => opt(v, p.sector)).join('')}
        </select></div>
    </div>
    <div class="field-row">
      <div class="field"><label for="customer_type">Who do you mainly serve?</label>
        <select class="select" id="customer_type" name="customer_type" required>
          ${['', 'Consumers (B2C)', 'Businesses (B2B)', 'Both consumers and businesses', 'Mostly online buyers'].map(v => `<option value="${esc(v)}" ${v === (p.customer_type || '') ? 'selected' : ''}>${v ? esc(v) : 'Choose one…'}</option>`).join('')}
        </select>
        <div class="hint">This shapes the examples and the offer advice you get.</div></div>
      <div class="field"><label for="stage">Stage</label>
        <select class="select" id="stage" name="stage" required>${['Idea', 'Starting', 'Growing', 'Established'].map(v => opt(v, p.stage)).join('')}</select></div>
    </div>
    <div class="field-row">
      <div class="field"><label for="team_size">Team size</label>
        <select class="select" id="team_size" name="team_size" required>${['Just me', '2–5', '6–10', '11–20', '20+'].map(v => opt(v, p.team_size)).join('')}</select></div>
      <div class="field"><label for="years">Years operating</label>
        <select class="select" id="years" name="years" required>${['Under 1 year', '1–3 years', '3–5 years', '5–10 years', '10+ years'].map(v => opt(v, p.years)).join('')}</select></div>
    </div>
    <div class="field"><label for="revenue_band">Monthly revenue</label>
      <select class="select" id="revenue_band" name="revenue_band" required>
        ${['Pre-revenue', 'Under RM10,000', 'RM10,000–RM20,000', 'RM20,000–RM50,000', 'RM50,000–RM100,000', 'Above RM100,000'].map(v => opt(v, p.revenue_band)).join('')}
      </select></div>
    <div class="field"><label for="main_challenge">What is the main challenge you want to fix?</label>
      <textarea class="textarea" id="main_challenge" name="main_challenge" placeholder="e.g. Profit is inconsistent even when sales look busy." required>${esc(p.main_challenge || '')}</textarea>
      <div class="hint">Be specific. This is used to frame your results and coaching, not shared publicly.</div></div>
    <div class="row" style="justify-content:flex-end;gap:8px">
      ${profile ? `<button type="button" class="btn btn-ghost" data-action="cancel-profile">Cancel</button>` : ''}
      <button class="btn btn-primary" type="submit">Save business profile ${icon('right', 14)}</button>
    </div>
  </form>`;
}

function deltaChip(value) {
  if (value == null || value === 0) return '';
  const up = value > 0;
  return `<span class="chip ${up ? 'chip-teal' : 'chip-red'}" title="Change since your previous check-up">${up ? '+' : ''}${value}</span>`;
}

function checkupResults(data, profile, history = []) {
  const result = data.result || data;
  const scores = result.components || {};
  const change = data.change || null;
  const previous = data.previous || null;
  const ranked = Object.keys(scores).sort((a, b) => scores[a] - scores[b]);
  const priorities = data.priorities || ranked.slice(0, 3).map(id => ({
    component: id, name: compName(id), score: scores[id], recommendation: DIAG_RECS[id],
    available: compMeta(id).available, module_id: compMeta(id).module_id || null, lessons: [],
  }));
  const strengths = data.strengths || ranked.slice(-2).reverse().map(id => ({ component: id, name: compName(id), score: scores[id] }));
  const firstModule = priorities.find(pr => pr.available && pr.module_id);
  return `
  <div class="card result-hero">
    <div class="copy">
      <div class="eyebrow">Business Check-Up · ${fmtDate(result.created_at)}</div>
      <h2>${result.overall >= 70 ? 'A solid base — now make it systematic.' : result.overall >= 50 ? 'Practical experience, uneven structure.' : 'You have room to build strong foundations.'}</h2>
      <p>You answered the diagnostic for <b>${esc(profile ? profile.business_name : 'your business')}</b>. Strongest areas: ${strengths.map(s => `${esc(s.name)} (${s.score}%)`).join(', ')}. The priorities below are ordered by the lowest scores.</p>
      ${change ? `<div class="row wrap" style="gap:7px;margin-top:10px">
        <span class="chip ${change.overall >= 0 ? 'chip-teal' : 'chip-red'}">${change.overall >= 0 ? '+' : ''}${change.overall} points since ${fmtDate(previous.created_at)}</span>
        <span class="chip chip-grey">Self-assessment, not a pass</span>
      </div>` : ''}
      <div class="row wrap" style="gap:8px;margin-top:14px">
        <a class="btn btn-primary btn-sm" href="#/learn/${firstModule ? esc(firstModule.module_id) : 'strategy'}">${firstModule ? `Start ${esc(firstModule.name)}` : 'Start Business Strategy & Model'} ${icon('right', 13)}</a>
        <button class="btn btn-outline btn-sm" type="button" data-action="retake-checkup">${icon('refresh', 13)} Retake check-up</button>
      </div>
    </div>
    <div class="score-badge">${ring(result.overall, 122, 9, 'diagnostic', true)}</div>
  </div>

  <div class="section">
    <div class="section-head"><div><h2>Recommended learning priorities</h2><p>Areas scoring below 85% where a small change is likely to help most.</p></div></div>
    ${priorities.length ? `<div class="grid auto-260">
      ${priorities.map((pr, i) => `<div class="priority-card ${i === 0 ? 'top' : ''}">
        <div class="row-between"><span class="rank">Priority ${i + 1}</span><span class="chip ${i === 0 ? 'chip-yellow' : 'chip-grey'}">${pr.score}%</span></div>
        <h4>${esc(pr.name)}</h4>
        <p>${esc(pr.recommendation)}</p>
        ${pr.available && pr.module_id ? `<a class="link-arrow" href="#/learn/${esc(pr.module_id)}">Start the module ${icon('right', 12)}</a>
          ${pr.lessons && pr.lessons.length ? `<div class="tiny muted" style="margin-top:6px">Starts with: ${pr.lessons.map(esc).join(' · ')}</div>` : ''}`
          : `<span class="chip chip-grey">Module in development</span>`}
      </div>`).join('')}
    </div>` : `<div class="card card-pad">
      <p class="small" style="margin:0 0 10px"><b>No urgent gaps.</b> Every component scored 85% or higher. Pick one area to deepen rather than chasing a weakness.</p>
      <a class="btn btn-outline btn-sm" href="#/learn">Open the modules ${icon('right', 13)}</a>
    </div>`}
  </div>

  <div class="section split">
    <div class="card card-pad">
      <div class="card-head"><div><h2>Component breakdown</h2><p>Knowledge and practice across all eight areas.</p></div></div>
      <div class="band-list">
        ${Object.keys(scores).map(id => `<div class="band">
          <span class="nm">${esc(compName(id))}</span>
          ${bar(scores[id], scores[id] >= 70 ? '' : scores[id] >= 50 ? 'yellow' : 'navy')}
          <span class="vl">${scores[id]}%</span>
          ${change && change.components[id] != null ? deltaChip(change.components[id]) : ''}
        </div>`).join('')}
      </div>
    </div>
    <div class="card card-pad">
      <h2 style="font-size:16px;margin-bottom:10px">What this means</h2>
      <p class="small muted">The check-up is a baseline, not a certificate. It shows where your current knowledge and practice are uneven. Mastery levels on your progress page are only assigned from scored assessments and verified module work.</p>
      <hr class="hr">
      <div class="row-between" style="margin-bottom:8px"><span class="small strong">Strongest</span><span class="chip chip-teal">${esc(strengths[0] ? strengths[0].name : '—')}</span></div>
      <div class="row-between"><span class="small strong">Biggest gap</span><span class="chip chip-yellow">${esc(priorities[0] ? priorities[0].name : '—')}</span></div>
      <hr class="hr">
      <a class="btn btn-soft btn-block btn-sm" href="#/progress">View full progress record ${icon('right', 13)}</a>
    </div>
  </div>

  ${history.length > 1 ? `<div class="section card card-pad">
    <div class="card-head"><div><h2>Check-up history</h2><p>Every diagnostic is stored. Compare what actually moved.</p></div></div>
    <div class="table-wrap"><table class="table">
      <thead><tr><th>Date</th><th>Overall</th><th>Change</th><th>Weakest area</th></tr></thead>
      <tbody>${history.map((h, i) => {
        const prev = history[i + 1];
        const delta = prev ? h.overall - prev.overall : null;
        const weakest = Object.entries(h.components || {}).sort((a, b) => a[1] - b[1])[0];
        return `<tr><td class="tiny">${fmtDate(h.created_at)}</td><td><b>${h.overall}%</b></td>
          <td>${delta == null ? '<span class="tiny muted">first</span>' : deltaChip(delta)}</td>
          <td class="tiny muted">${weakest ? `${esc(compName(weakest[0]))} (${weakest[1]}%)` : '—'}</td></tr>`;
      }).join('')}</tbody>
    </table></div>
  </div>` : ''}`;
}

async function viewCheckup(my) {
  const data = await api('/api/checkup');
  if (my !== seq) return;
  const profile = data.profile;
  const result = state.checkupResult || data.result;

  if (!profile || state.editProfile) {
    mount(`
      <div class="section-head" style="margin-top:0"><div><div class="eyebrow">Step 1 · Business Check-Up</div><h1>Tell us about your business</h1><p>A few details so the diagnostic and recommendations fit your reality. You can edit this at any time.</p></div></div>
      <div class="split">
        <div class="card card-pad">${profileForm(profile)}</div>
        <div class="card card-pad">
          <h3 style="margin-bottom:10px">Why we ask</h3>
          <p class="small muted">Your sector and stage change what “good” looks like. A food stall at RM30,000 a month and a service business at the same revenue have different cost structures and risks.</p>
          <hr class="hr">
          <div class="diag-cats">
            ${state.components.map((c, i) => `<div class="diag-cat"><span class="num">${String(i + 1).padStart(2, '0')}</span>${esc(c.name)}</div>`).join('')}
          </div>
          <hr class="hr">
          <p class="tiny muted">Your profile is stored on the server with your account and used only inside this workspace.</p>
        </div>
      </div>`, my);
    return;
  }

  if (result) {
    mount(`
      <div class="section-head" style="margin-top:0">
        <div><div class="eyebrow">Business Check-Up</div><h1>Your diagnostic results</h1></div>
        <button class="btn btn-outline btn-sm" type="button" data-action="edit-profile">${icon('edit', 13)} Edit business profile</button>
      </div>
      <div class="profile-summary" style="margin-bottom:18px">
        <div><div class="k">Business</div><div class="v">${esc(profile.business_name)}</div></div>
        <div><div class="k">Sector</div><div class="v">${esc(profile.sector)}</div>${profile.customer_type ? `<div class="tiny muted">${esc(profile.customer_type)}</div>` : ''}</div>
        <div><div class="k">Stage</div><div class="v">${esc(profile.stage)} · ${esc(profile.team_size)} people</div></div>
        <div><div class="k">Main challenge</div><div class="v" style="font-weight:500;font-size:12px">${esc(profile.main_challenge)}</div></div>
      </div>
      ${checkupResults(state.checkupResult || data, profile, data.history || [])}`, my);
    return;
  }

  mount(`
    <div class="section-head" style="margin-top:0">
      <div><div class="eyebrow">Business Check-Up</div><h1>Find your real gaps, not the ones you assume.</h1>
      <p>24 practical questions across the eight components. About 8 minutes. No preparation needed — answer as your business actually runs today.</p></div>
      <button class="btn btn-outline btn-sm" type="button" data-action="edit-profile">${icon('edit', 13)} Edit profile</button>
    </div>
    <div class="card card-pad">
      <div class="diag-intro">
        <div>
          <div class="profile-summary" style="margin-bottom:18px">
            <div><div class="k">Business</div><div class="v">${esc(profile.business_name)}</div></div>
            <div><div class="k">Sector</div><div class="v">${esc(profile.sector)}</div></div>
            <div><div class="k">Stage</div><div class="v">${esc(profile.stage)}</div></div>
            <div><div class="k">Revenue</div><div class="v">${esc(profile.revenue_band)}</div></div>
          </div>
          <h2 style="font-size:18px;margin-bottom:8px">What the diagnostic covers</h2>
          <div class="roadmap-note" style="margin-bottom:16px">
            ${icon('info', 15)}
            <div><b>This is a self-assessment, not a test.</b> There is no penalty for a low score and no certificate for a high one. Answer as your business actually runs today — that is the only way the priorities will be useful.</div>
          </div>
          <div class="diag-cats" style="margin-bottom:20px">
            ${state.components.map((c, i) => `<div class="diag-cat"><span class="num">${String(i + 1).padStart(2, '0')}</span>${esc(c.name)}</div>`).join('')}
          </div>
          <div class="row wrap">
            <button class="btn btn-primary btn-lg" type="button" data-action="start-checkup">Start the check-up ${icon('right', 15)}</button>
            <span class="tiny muted">24 questions · 8 minutes · results saved automatically</span>
          </div>
        </div>
        <div class="card" style="padding:18px;background:#F8FAFC;box-shadow:none">
          <div class="row" style="gap:8px;margin-bottom:8px">${icon('info', 15)}<b class="small">How scoring works</b></div>
          <p class="tiny muted">Each component is scored out of 100 from the questions you answer correctly. Your three lowest scores become recommended priorities. This is a baseline, not a pass or fail.</p>
        </div>
      </div>
    </div>`, my);
}

/* ------------------------------------------------------------------ runner */
function runnerHTML() {
  const r = state.runner;
  const q = r.questions[r.index];
  const total = r.questions.length;
  const selected = r.answers[q.id];
  const titles = { checkup: 'Business Check-Up', quiz: 'Knowledge quiz', scenario: 'Scenario test' };
  const subtitle = r.type === 'checkup' ? 'Diagnostic assessment' : r.type === 'quiz' ? 'Business Strategy & Model' : 'Real-world decisions';
  const dots = r.questions.map((qq, i) => `<span class="answer-dot ${r.answers[qq.id] !== undefined ? 'done' : ''} ${i === r.index ? 'cur' : ''}"></span>`).join('');
  const pct = Math.round((Object.keys(r.answers).length / total) * 100);
  return `<div class="runner">
    <div class="runner-top">
      <div>
        <div class="eyebrow" style="margin-bottom:3px">${titles[r.type]}</div>
        <div class="runner-meta">${subtitle} · Question <b>${r.index + 1}</b> of ${total}${r.pass_mark ? ` · pass mark ${r.pass_mark}%` : ''}</div>
      </div>
      <button class="btn btn-ghost btn-sm" type="button" data-action="exit-runner">${icon('close', 14)} Exit</button>
    </div>
    <div class="row" style="gap:12px;margin-bottom:8px">
      <div style="flex:1">${bar(pct)}</div>
      <span class="tiny muted" style="width:34px;text-align:right">${pct}%</span>
    </div>
    <div class="answer-dots" style="margin-bottom:14px">${dots}</div>
    <div class="card qcard fade-in">
      <div class="row wrap" style="gap:6px;margin-bottom:10px">
        <span class="chip chip-navy">${esc(compName(q.component))}</span>
        <span class="chip chip-grey">${esc(q.topic)}</span>
      </div>
      <h2>${esc(q.prompt)}</h2>
      <div class="options">
        ${q.options.map((o, i) => `<button type="button" class="option ${selected === i ? 'sel' : ''}" data-action="answer" data-i="${i}">
          <span class="letter">${'ABCDEF'[i]}</span><span>${esc(o)}</span></button>`).join('')}
      </div>
      <div class="qnav">
        <button class="btn btn-ghost" type="button" data-action="runner-back" ${r.index === 0 ? 'disabled' : ''}>${icon('left', 14)} Back</button>
        <span class="tiny muted">${selected !== undefined ? 'Answer selected' : 'Choose one answer'}</span>
        ${r.index === total - 1
          ? `<button class="btn btn-teal" type="button" data-action="runner-submit">Submit ${r.type === 'checkup' ? 'check-up' : 'answers'} ${icon('check', 14)}</button>`
          : `<button class="btn btn-primary" type="button" data-action="runner-next">Next ${icon('right', 14)}</button>`}
      </div>
    </div>
    <p class="tiny muted center" style="margin-top:14px">Answers are scored on the server. You can move back and change an answer before submitting.</p>
  </div>`;
}

function renderRunner() {
  const my = begin();
  mount(runnerHTML(), my);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function startCheckup() {
  try {
    const data = await api('/api/checkup');
    state.runner = { type: 'checkup', questions: data.questions, index: 0, answers: {} };
    state.checkupResult = null;
    renderRunner();
  } catch (err) { toast(err.message, 'err'); }
}

async function startAssessment(kind) {
  try {
    const data = await api('/api/assessment/' + kind + '/questions');
    state.assessmentResult = null;
    state.runner = {
      type: kind, questions: data.questions, index: 0, answers: {},
      pass_mark: data.pass_mark, history: data.history,
    };
    renderRunner();
  } catch (err) { toast(err.message, 'err'); }
}

async function submitRunner() {
  const r = state.runner;
  if (!r) return;
  const unanswered = r.questions.filter(q => r.answers[q.id] === undefined);
  if (unanswered.length) {
    r.index = r.questions.findIndex(q => r.answers[q.id] === undefined);
    renderRunner();
    toast('Please answer all questions before submitting. ' + unanswered.length + ' remaining.', 'err');
    return;
  }
  const btn = $('[data-action="runner-submit"]');
  if (btn) { btn.disabled = true; btn.textContent = 'Scoring…'; }
  try {
    const endpoint = r.type === 'checkup' ? '/api/checkup/submit' : '/api/assessment/' + r.type + '/submit';
    const data = await api(endpoint, { method: 'POST', body: JSON.stringify({ answers: r.answers }) });
    if (r.type === 'checkup') {
      state.checkupResult = data;
      state.progress = data.progress;
      state.runner = null;
      location.hash = '#/checkup';
      router();
    } else {
      state.assessmentResult = data;
      state.progress = data.progress;
      state.runner = null;
      viewTest(begin(), r.type);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = 'Submit answers'; }
    toast(err.message, 'err');
  }
}

/* ------------------------------------------------------------------ learn */
async function viewLearn(my) {
  const p = state.progress || await api('/api/progress');
  if (my !== seq) return;
  state.progress = p;
  const liveModules = state.components.filter(c => c.available).length;
  mount(`
    <div class="section-head" style="margin-top:0">
      <div><div class="eyebrow">Learn &amp; Improve</div><h1>Pick a skill. Use it this week.</h1>
      <p>${liveModules} of ${state.components.length} modules live. Short lessons, real numbers, templates you can actually use.</p></div>
      <span class="chip chip-yellow">🔥 ${p.module.lessons_done} lessons done</span>
    </div>
    <div class="grid auto-300">
      ${state.components.map((c, i) => {
        const style = compStyle(c.id);
        const comp = p.components.find(x => x.id === c.id);
        const isCurrent = p.module.id === c.module_id;
        if (c.available) {
          return `<div class="comp-card available">
            <div class="top"><span class="comp-emoji" aria-hidden="true">${style.emoji}</span><span class="chip chip-teal">Live</span></div>
            <h3>${esc(c.name)}</h3>
            <p>${esc(style.short)}</p>
            ${isCurrent ? `<div style="margin-top:2px">${bar(p.module.percent)}<div class="row-between" style="margin-top:6px"><span class="tiny muted">${p.module.percent}% complete</span><span class="tiny muted">${p.module.lessons_done}/${p.module.lessons_total} lessons</span></div></div>` : ''}
            <div class="foot"><span class="meta">${isCurrent && p.module.passed ? 'Passed ✓' : (isCurrent ? 'In progress' : 'Ready when you are')}</span>
              <a class="btn btn-primary btn-sm" href="#/learn/${esc(c.module_id)}">${isCurrent && p.module.lessons_done ? 'Continue' : 'Start'} ${icon('right', 12)}</a></div>
          </div>`;
        }
        return `<div class="comp-card locked">
          <div class="top"><span class="comp-emoji" aria-hidden="true">${style.emoji}</span><span class="ribbon">Soon</span></div>
          <h3>${esc(c.name)}</h3>
          <p>${esc(style.short)}</p>
          <div class="foot"><span class="meta">${comp && comp.score != null ? 'Check-up ' + comp.score + '%' : 'Not assessed yet'}</span>
            <span class="chip chip-grey">${icon('lock', 11)} Locked</span></div>
        </div>`;
      }).join('')}
    </div>`, my);
}

async function viewModule(my, moduleId = 'strategy') {
  const data = await api('/api/module/' + encodeURIComponent(moduleId));
  if (my !== seq) return;
  state.moduleData = data;
  const m = data.module;
  const st = data.state;
  const moduleIndex = Math.max(0, state.components.findIndex(c => c.id === m.component));
  const assessmentsLive = m.id === 'strategy';
  const done = new Set(data.lessons_done);
  const practical = st.practical;
  const lessonCheck = st.lessons_done === st.lessons_total ? `${st.lessons_done}/${st.lessons_total} complete` : `${st.lessons_done}/${st.lessons_total} lessons`;
  const cp = assessmentsLive ? [
    { b: 'Lessons', s: lessonCheck, done: st.lessons_done === st.lessons_total },
    { b: 'Knowledge quiz', s: st.quiz ? `Best ${st.quiz.score}%` : `Pass ${st.standards.quiz_pass}%`, done: st.quiz_passed },
    { b: 'Scenario test', s: st.scenario ? `Best ${st.scenario.score}%` : `Pass ${st.standards.scenario_pass}%`, done: st.scenario_passed },
    { b: 'Practical', s: practical ? (practical.status === 'reviewed' ? `Scored ${practical.average}/4` : 'Awaiting review') : `Rubric ${st.standards.rubric_min}/4`, done: st.practical_passed },
  ] : [{ b: 'Lessons', s: lessonCheck, done: st.lessons_done === st.lessons_total }];
  const LESSON_ART = ['/static/img/lesson-map.svg', '/static/img/lesson-lens.svg', '/static/img/lesson-check.svg', '/static/img/lesson-boost.svg'];
  const LESSON_EMOJI = ['🧠', '🔍', '✅', '🚀'];

  mount(`
    <div class="row" style="gap:8px;margin-bottom:14px">
      <a class="link-arrow" href="#/learn">${icon('left', 13)} All components</a>
      <span class="chip chip-grey">Module ${moduleIndex + 1} of ${state.components.length || 8}</span>
    </div>
    <section class="module-hero">
      <div class="eyebrow" style="color:var(--sun)">${esc(m.level)} module · ${esc(compName(m.component))}</div>
      <h1>${esc(m.title)}</h1>
      <p>${esc(m.tagline)}</p>
      <div class="meta">
        <span class="chip">${icon('clock', 12)} ${esc(m.hours)}</span>
        <span class="chip">${icon('learn', 12)} ${m.lessons.length} lessons</span>
        ${assessmentsLive ? `<span class="chip">${icon('test', 12)} Quiz · scenario · practical</span>` : `<span class="chip">${icon('download', 12)} Content module</span>`}
        <span class="chip">${icon('download', 12)} ${m.templates.length} templates</span>
      </div>
    </section>

    <div class="section split">
      <div class="card card-pad">
        <div class="row-between" style="margin-bottom:10px"><h3>Module progress</h3><span class="small strong">${st.percent}%</span></div>
        ${bar(st.percent)}
        <p class="small muted" style="margin-top:10px">${esc(m.outcome)}</p>
        <div class="checkpoint-grid" style="margin-top:14px">
          ${cp.map(c => `<div class="checkpoint ${c.done ? 'done' : ''}"><span class="tick">${c.done ? icon('check', 11) : ''}</span><div><b>${c.b}</b><span>${esc(c.s)}</span></div></div>`).join('')}
        </div>
      </div>
      ${assessmentsLive ? `<div class="card card-pad" style="background:${st.passed ? 'linear-gradient(150deg,#FFF7D6,#FFF0B0)' : '#F8FAFC'};border-color:${st.passed ? '#F3DC8A' : 'var(--line)'}">
        <div class="eyebrow" style="color:${st.passed ? '#6A4B00' : 'var(--teal-600)'}">${st.passed ? '✓ Module verified' : 'Pass standard'}</div>
        <h3 style="color:var(--ink);font-size:18px;margin-bottom:8px">${st.passed ? 'Module complete' : 'All three criteria required'}</h3>
        <p class="small" style="color:${st.passed ? '#5C511F' : 'var(--muted)'}">${st.passed ? 'Your quiz, scenario and reviewed practical are all verified. This result counts toward your mastery level.' : `Knowledge quiz ${st.standards.quiz_pass}% · scenario test ${st.standards.scenario_pass}% · practical rubric ${st.standards.rubric_min}/4 with no criterion below 2. Retries are unlimited.`}</p>
        <div style="margin-top:14px">
          ${practical && practical.status === 'pending' ? `<span class="chip chip-yellow">${icon('clock', 11)} Practical awaiting review</span>` : ''}
          ${st.passed ? `<a class="btn btn-primary btn-sm" href="#/progress">See verified progress ${icon('right', 12)}</a>` : `<a class="btn btn-primary btn-sm" href="#/test">Go to assessments ${icon('right', 12)}</a>`}
        </div>
      </div>` : `<div class="card card-pad" style="background:#F8FAFC">
        <div class="eyebrow" style="color:var(--teal-600)">Content module</div>
        <h3 style="font-size:18px;margin-bottom:8px">Lessons and templates are live</h3>
        <p class="small muted">The scored assessments for this module are being wired in Phase 5. You can read every lesson, complete them, and download the templates now — no assessment result is recorded yet.</p>
        <div style="margin-top:14px"><a class="btn btn-outline btn-sm" href="#/learn">Back to modules ${icon('right', 12)}</a></div>
      </div>`}
    </div>

    <div class="section">
      <div class="section-head"><div><h2>Lessons</h2><p>Short reps, not a textbook. Open one, read the story, do the move.</p></div></div>
      ${m.lessons.map((l, i) => {
        const isOpen = (i === Math.min(st.lessons_done, m.lessons.length - 1) && !done.has(l.id)) || (i === 0 && st.lessons_done === 0);
        return `<details class="lesson ${done.has(l.id) ? 'done' : ''}" ${isOpen ? 'open' : ''}>
        <summary>
          <span class="lesson-emoji" aria-hidden="true">${LESSON_EMOJI[i % 4]}</span>
          <span class="lsum"><span class="lesson-kicker">Lesson ${String(l.number).padStart(2, '0')}</span><b>${esc(l.title)}</b><span>${esc(l.summary)}</span></span>
          <span class="lmeta">${done.has(l.id) ? '<span class="chip chip-teal">Done</span>' : ''}<span class="min">${l.minutes} min</span>${icon('chevron', 16)}</span>
        </summary>
        <div class="lesson-body">
          <div class="lesson-hero">
            <img class="lesson-art" src="${LESSON_ART[i % 4]}" alt="" width="360" height="220" loading="lazy">
            <div class="lesson-hero-copy">
              <span class="story-kicker">Why it matters</span>
              <p>${esc(l.why)}</p>
            </div>
          </div>

          <div class="lesson-copy">
            ${l.explanation.map((text, k) => `<p class="${k === 0 ? 'lead' : ''}">${esc(text)}</p>`).join('')}
          </div>

          <div class="case-file">
            <div class="case-tag">📌 Case file</div>
            <h4>${esc(l.example.title)}</h4>
            <p>${esc(l.example.text)}</p>
          </div>

          <div class="pair-grid">
            <div class="pair-box do"><h5>✅ Do this</h5><ul>${l.do.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
            <div class="pair-box dont"><h5>🚫 Not this</h5><ul>${l.dont.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
          </div>

          <details class="redflags">
            <summary>⚠️ Common mistakes <span>${l.mistakes.length}</span></summary>
            <ul>${l.mistakes.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
          </details>

          <div class="mission">
            <div class="mission-head">
              <span class="mission-icon" aria-hidden="true">🎯</span>
              <div><span class="story-kicker">Your move</span><h4>${esc(l.exercise.prompt)}</h4></div>
            </div>
            <ol>${l.exercise.steps.map(s => `<li>${esc(s)}</li>`).join('')}</ol>
            <div class="mission-foot">
              ${done.has(l.id)
                ? `<span class="chip chip-teal">${icon('check', 11)} Lesson complete</span>`
                : `<button class="btn btn-primary btn-sm" type="button" data-action="lesson-complete" data-id="${l.id}">Mark complete ${icon('check', 13)}</button>`}
            </div>
          </div>
        </div>
      </details>`;
      }).join('')}
    </div>

    <div class="section split">
      <div class="card card-pad">
        <div class="card-head"><div><h2>Downloadable templates</h2><p>Use these with your own numbers. Files are served directly from futurePreneur.</p></div></div>
        ${m.templates.map(t => `<div class="template-row">
          <span class="file-icon">${esc((t.format || 'FILE').slice(0, 3).toUpperCase())}</span>
          <div style="min-width:0"><div class="fname">${esc(t.title)}</div><div class="fmeta">${esc(t.description)}${t.source === 'file' ? ' · Your file' : ''}</div></div>
          <a class="btn btn-outline btn-sm dl" href="/api/templates/${esc(t.slug)}" download>${icon('download', 13)} Download</a>
        </div>`).join('')}
      </div>
      ${assessmentsLive ? `<div class="card card-pad">
        <h2 style="font-size:16px;margin-bottom:6px">Ready to test it?</h2>
        <p class="small muted" style="margin-bottom:14px">Each assessment is scored on the server. Your best verified results stay on your record.</p>
        ${[
          { k: 'quiz', t: 'Knowledge quiz', s: st.quiz ? `Best ${st.quiz.score}%` : `${st.standards.quiz_pass}% to pass`, ok: st.quiz_passed },
          { k: 'scenario', t: 'Scenario test', s: st.scenario ? `Best ${st.scenario.score}%` : `${st.standards.scenario_pass}% to pass`, ok: st.scenario_passed },
          { k: 'practical', t: 'Practical assignment', s: practical ? (practical.status === 'reviewed' ? `Scored ${practical.average}/4` : 'Awaiting review') : `Rubric ${st.standards.rubric_min}/4`, ok: st.practical_passed },
        ].map(x => `<a href="#/test/${x.k}" class="row-between" style="padding:11px 0;border-bottom:1px solid var(--line);color:inherit">
          <div class="row" style="gap:10px"><span class="icon-tile ${x.ok ? 'teal' : ''}" style="width:30px;height:30px;border-radius:8px">${x.ok ? icon('check', 14) : icon('test', 14)}</span>
          <div><div class="small strong">${x.t}</div><div class="tiny muted">${esc(x.s)}</div></div></div>
          ${icon('right', 14)}
        </a>`).join('')}
      </div>` : `<div class="card card-pad">
        <h2 style="font-size:16px;margin-bottom:6px">Assessments</h2>
        <p class="small muted" style="margin:0">Quiz, scenario and practical for this module arrive in Phase 5. Lesson progress and template downloads are recorded now.</p>
      </div>`}
    </div>`, my);
}

/* ------------------------------------------------------------------ tests */
async function viewTest(my, sub) {
  if (sub === 'quiz' || sub === 'scenario') {
    if (state.assessmentResult && state.assessmentResult.kind === sub) {
      renderAssessmentResult(state.assessmentResult, my);
      return;
    }
    await startAssessment(sub);
    return;
  }
  if (sub === 'practical') {
    await viewPractical(my);
    return;
  }
  const p = await api('/api/progress');
  if (my !== seq) return;
  state.progress = p;
  const st = p.module;
  const cards = [
    {
      cls: '', icon: 'learn', title: 'Knowledge quiz', count: '10 questions',
      desc: 'Multiple choice on the core ideas: models, contribution, break-even, priorities.',
      pass: st.standards.quiz_pass + '%', result: st.quiz, key: 'quiz',
      time: '8 min',
    },
    {
      cls: 'yellow', icon: 'briefcase', title: 'Scenario test', count: '5 scenarios',
      desc: 'Real decisions from food, online-selling and service businesses. Choose the soundest response.',
      pass: st.standards.scenario_pass + '%', result: st.scenario, key: 'scenario',
      time: '10 min',
    },
    {
      cls: 'navy', icon: 'edit', title: 'Practical assignment', count: '4 written answers',
      desc: 'Apply the module to your own business. Reviewed against a four-part rubric.',
      pass: st.standards.rubric_min + '/4', result: st.practical ? { score: practicalPct(st.practical), passed: st.practical.passed } : null, key: 'practical',
      time: '25 min',
    },
  ];
  mount(`
    <div class="section-head" style="margin-top:0">
      <div><div class="eyebrow">Test Your Skills</div><h1>Prove it — with your own business.</h1>
      <p>Knowledge tells you what the idea is. Scenarios test judgement. The practical assignment proves you can apply it. All three are required to pass the module.</p></div>
      <a class="btn btn-outline btn-sm" href="#/learn/strategy">${icon('learn', 13)} Back to module</a>
    </div>
    <div class="grid auto-300">
      ${cards.map(c => {
        const r = c.result;
        const passed = r && r.passed;
        const meta = !r ? 'Not attempted' : c.key === 'practical'
          ? (r.status === 'reviewed' ? 'Scored ' + r.average + '/4' : 'Awaiting review')
          : 'Best ' + r.score + '% · ' + (r.attempts || 1) + (r.attempts === 1 ? ' attempt' : ' attempts');
        return `<div class="assessment-card ${c.cls}">
          <div class="head"><span class="icon-tile ${c.cls === 'yellow' ? 'yellow' : c.cls === 'navy' ? 'navy' : 'teal'}">${icon(c.icon, 18)}</span>
            ${passed ? `<span class="chip chip-green">${icon('check', 11)} Passed</span>` : r ? `<span class="chip chip-grey">In progress</span>` : `<span class="chip chip-grey">Not attempted</span>`}</div>
          <div><h3>${c.title}</h3><p>${c.desc}</p></div>
          <div class="meta-row"><span>${icon('clock', 11)} ${c.time}</span><span><b>${c.count}</b></span><span>Pass <b>${c.pass}</b></span></div>
          <div class="foot"><span class="tiny muted">${esc(meta)}</span>
            <a class="btn ${passed ? 'btn-outline' : 'btn-primary'} btn-sm" href="#/test/${c.key}">${passed ? 'Review / retake' : r ? 'Continue' : 'Start'} ${icon('right', 12)}</a></div>
        </div>`;
      }).join('')}
    </div>

    <div class="section split">
      <div class="card card-pad">
        <div class="card-head"><div><h2>Pass standard</h2><p>Set by the platform administrator and enforced on the server.</p></div></div>
        <div class="checklist">
          <div class="checklist-row"><span class="tick">${icon('check', 11)}</span><div class="txt">Knowledge quiz <span>Multiple choice, automatically scored</span></div><b class="small">${st.standards.quiz_pass}%</b></div>
          <div class="checklist-row"><span class="tick">${icon('check', 11)}</span><div class="txt">Scenario test <span>Applied judgement, automatically scored</span></div><b class="small">${st.standards.scenario_pass}%</b></div>
          <div class="checklist-row"><span class="tick">${icon('check', 11)}</span><div class="txt">Practical assignment <span>Four criteria, scored 0–4 by a reviewer</span></div><b class="small">≥ ${st.standards.rubric_min}/4</b></div>
        </div>
        <p class="tiny muted" style="margin-top:12px">Failed attempts are kept in your history. They never remove a previous pass, but they do show what needs revision. The module is marked passed only when all three criteria are verified.</p>
      </div>
      <div class="card card-pad">
        <h2 style="font-size:16px;margin-bottom:8px">Before you start</h2>
        <p class="small muted">The quiz and scenario give immediate feedback with explanations. Review wrong answers before retrying — retries are unlimited, but guessing your way through teaches you very little.</p>
        <hr class="hr">
        <div class="row" style="gap:8px;margin-bottom:8px">${icon('alert', 15)}<b class="small">No fake results</b></div>
        <p class="tiny muted">Scores are computed on the server from the stored answer key. Practical work is only marked passed after a reviewer scores it. There are no automatic certificates.</p>
      </div>
    </div>`, my);
}

function practicalPct(s) {
  return s && s.average ? Math.round((s.average / 4) * 100) : 0;
}

function renderAssessmentResult(data, my) {
  const passed = data.passed;
  const title = data.kind === 'quiz' ? 'Knowledge quiz' : 'Scenario test';
  const nextHref = data.kind === 'quiz' ? '#/test/scenario' : '#/test/practical';
  const nextLabel = data.kind === 'quiz' ? 'Continue to scenario test' : 'Continue to practical';
  mount(`
    <div class="row" style="gap:8px;margin-bottom:14px"><a class="link-arrow" href="#/test">${icon('left', 13)} Assessment centre</a>
      <span class="chip chip-grey">${esc(title)}</span></div>
    <div class="verdict ${passed ? '' : 'fail'}">
      <div class="vicon">${passed ? icon('check', 22) : icon('refresh', 20)}</div>
      <div style="flex:1"><h3>${passed ? 'Passed — ' + data.score + '%' : 'Not passed — ' + data.score + '%'}</h3>
        <p>${passed ? 'You met the ' + data.pass_mark + '% standard. ' + (data.kind === 'quiz' ? 'Next, test your judgement in the scenario test.' : 'Next, apply it in the practical assignment.') : 'You need ' + data.pass_mark + '% to pass. Review the explanations below, then retry when ready.'}</p></div>
      <div class="score-badge"><div class="num">${data.correct}<small>/${data.total}</small></div><div class="lbl">correct</div></div>
    </div>

    <div class="section grid auto-260">
      <div class="stat"><div class="k">Your score</div><div class="v">${data.score}<small>%</small></div><div class="s">Pass mark ${data.pass_mark}%</div></div>
      <div class="stat"><div class="k">Correct answers</div><div class="v">${data.correct}<small> / ${data.total}</small></div><div class="s">Scored on the server</div></div>
      <div class="stat"><div class="k">Module status</div><div class="v" style="font-size:19px;margin-top:10px">${data.progress.module.percent}%</div><div class="s">${data.progress.module.passed ? 'Module verified' : 'Criteria remaining'}</div></div>
    </div>

    <div class="section">
      <div class="section-head"><div><h2>Question feedback</h2><p>Every answer, with the reasoning. Use this to decide what to revise.</p></div></div>
      <div class="feedback-list">
        ${data.detail.map((d, i) => `<div class="feedback ${d.is_correct ? 'ok' : 'no'}">
          <div class="row-between" style="gap:10px"><span class="chip ${d.is_correct ? 'chip-teal' : 'chip-red'}">${d.is_correct ? 'Correct' : 'Review'}</span><span class="tiny muted">${esc(d.topic)}</span></div>
          <div class="fq" style="margin-top:7px">${i + 1}. ${esc(d.prompt)}</div>
          <div class="fa">Your answer: <b>${d.chosen != null ? esc(d.options[d.chosen]) : 'No answer'}</b></div>
          ${d.is_correct ? '' : `<div class="fa">Correct answer: <b>${esc(d.options[d.correct])}</b></div>`}
          <div class="fe">${esc(d.explanation)}</div>
        </div>`).join('')}
      </div>
    </div>

    <div class="section card card-pad">
      <div class="row-between wrap" style="gap:12px">
        <div><h3 style="margin-bottom:4px">${passed ? 'Keep the momentum' : 'Revise, then retake'}</h3>
          <p class="small muted" style="margin:0">${passed ? 'Your result is saved. Complete the remaining criteria to finish the module.' : 'The relevant lesson is linked below; retries are unlimited and your best pass is what counts.'}</p></div>
        <div class="row wrap">
          <a class="btn btn-outline" href="#/learn/strategy">${icon('learn', 14)} Review lessons</a>
          <button class="btn btn-primary" type="button" data-action="retry-assessment" data-kind="${data.kind}">${icon('refresh', 14)} Retry</button>
          ${passed ? `<a class="btn btn-teal" href="${nextHref}">${nextLabel} ${icon('right', 14)}</a>` : ''}
        </div>
      </div>
    </div>`, my);
}

/* ------------------------------------------------------------------ practical */
async function viewPractical(my) {
  const data = await api('/api/practical');
  if (my !== seq) return;
  const sub = data.submission;
  const showForm = state.practicalForm || !sub || (sub.status === 'reviewed' && !sub.passed);
  const standard = data.standards;

  if (showForm) {
    const existing = sub ? sub.responses : {};
    mount(`
      <div class="row" style="gap:8px;margin-bottom:14px"><a class="link-arrow" href="#/test">${icon('left', 13)} Assessment centre</a>
        <span class="chip chip-grey">Practical assignment</span></div>
      <div class="section-head" style="margin-top:0">
        <div><div class="eyebrow">Test Your Skills · Practical</div><h1>${esc(data.practical.title)}</h1>
        <p>${esc(data.practical.intro)}</p></div>
      </div>
      <div class="split">
        <div class="card card-pad">
          <form data-form="practical">
            ${data.practical.prompts.map((pr, i) => `<div class="field">
              <label for="${pr.id}">${i + 1}. ${esc(pr.label)}</label>
              <textarea class="textarea" id="${pr.id}" name="${pr.id}" rows="5" placeholder="${esc(pr.placeholder)}" required minlength="30">${esc(existing[pr.id] || '')}</textarea>
              <div class="hint">Criterion: ${esc(data.practical.criteria.find(c => c.id === pr.criterion).label)} · minimum 30 characters</div>
            </div>`).join('')}
            <div class="row-between wrap" style="gap:10px">
              <span class="tiny muted">${icon('shield', 12)} Saved to your account. Reviewed by an administrator.</span>
              <button class="btn btn-primary" type="submit">Submit for review ${icon('right', 14)}</button>
            </div>
          </form>
        </div>
        <div>
          <div class="card card-pad">
            <h3 style="margin-bottom:10px">How it is scored</h3>
            ${data.practical.criteria.map(c => `<div style="padding:8px 0;border-bottom:1px solid var(--line)">
              <div class="small strong">${esc(c.label)}</div><div class="tiny muted">${esc(c.hint)}</div></div>`).join('')}
            <p class="tiny muted" style="margin-top:12px">Each criterion is scored 0–4. Pass: average ≥ ${standard.rubric_min} with no criterion below ${standard.rubric_floor}. Your submission stays “awaiting review” until an administrator scores it — the module is not marked passed before then.</p>
          </div>
          <div class="card card-pad" style="margin-top:14px;background:#FFFBEF;border-color:#F2E5BB">
            <div class="row" style="gap:8px;margin-bottom:7px">${icon('alert', 15)}<b class="small">Use real numbers</b></div>
            <p class="tiny" style="color:#7A6420;margin:0">Write what is true for your business, including the parts you are unsure about. A specific, honest answer is easier to coach than a polished generic one.</p>
          </div>
        </div>
      </div>`, my);
    return;
  }

  const rubric = sub.rubric || {};
  mount(`
    <div class="row" style="gap:8px;margin-bottom:14px"><a class="link-arrow" href="#/test">${icon('left', 13)} Assessment centre</a>
      <span class="chip chip-grey">Practical assignment</span></div>
    <div class="section-head" style="margin-top:0">
      <div><div class="eyebrow">Practical assignment</div><h1>${sub.status === 'reviewed' ? (sub.passed ? 'Reviewed and passed' : 'Reviewed — revision needed') : 'Submitted for review'}</h1>
        <p>Submitted ${fmtDate(sub.created_at)}${sub.reviewed_at ? ' · reviewed ' + fmtDate(sub.reviewed_at) : ''}.</p></div>
      <span class="chip ${sub.status === 'reviewed' ? (sub.passed ? 'chip-teal' : 'chip-red') : 'chip-yellow'}">${sub.status === 'reviewed' ? (sub.passed ? 'Verified pass' : 'Not passed') : 'Awaiting review'}</span>
    </div>
    ${sub.status === 'reviewed' ? `
    <div class="card card-pad" style="margin-bottom:16px">
      <div class="row-between wrap" style="gap:14px">
        <div><div class="eyebrow">Rubric result</div><h2 style="font-size:20px">${sub.average} / 4 average</h2>
          <p class="small muted" style="margin:4px 0 0">Pass mark: ${standard.rubric_min}/4 average, no criterion below ${standard.rubric_floor}.</p></div>
        <a class="btn btn-outline btn-sm" href="#/progress">View progress record ${icon('right', 13)}</a>
      </div>
      <div class="grid auto-220" style="margin-top:16px">
        ${data.practical.criteria.map(c => `<div class="card" style="padding:13px;box-shadow:none">
          <div class="row-between"><span class="tiny muted">${esc(c.label)}</span><b class="small">${rubric[c.id] != null ? rubric[c.id] : '—'}/4</b></div>
          <div style="margin-top:7px">${bar(((rubric[c.id] || 0) / 4) * 100)}</div>
        </div>`).join('')}
      </div>
      ${sub.reviewer_note ? `<div class="example-box" style="margin-bottom:0"><div class="lbl">Reviewer note</div><p>${esc(sub.reviewer_note)}</p></div>` : ''}
    </div>` : `
    <div class="demo-banner" style="margin-bottom:16px">${icon('clock', 16)}<div><b>Awaiting review.</b> A reviewer will score this against the rubric. Your module stays <b>not yet passed</b> until that happens — results are never invented automatically.</div></div>`}

    <div class="card card-pad">
      <div class="card-head"><div><h2>Your submission</h2><p>What you wrote, kept as the record of this attempt.</p></div>
        ${sub.status === 'reviewed' && !sub.passed ? `<button class="btn btn-primary btn-sm" type="button" data-action="revise-practical">${icon('edit', 13)} Revise and resubmit</button>` : ''}</div>
      ${data.practical.prompts.map((pr, i) => `<div class="answer-block"><div class="k">${i + 1}. ${esc(pr.label)}</div><div class="v">${esc(sub.responses[pr.id] || '—')}</div></div>`).join('')}
    </div>`, my);
}

/* ------------------------------------------------------------------ progress */
async function viewProgress(my) {
  const p = await api('/api/progress');
  if (my !== seq) return;
  state.progress = p;
  const st = p.module;
  const levels = ['Beginner', 'Developing', 'Structured', 'Optimising'];
  const levelIdx = levels.indexOf(p.mastery.level);
  const criteria = [
    { t: `Lessons (${st.lessons_done}/${st.lessons_total})`, s: 'Mark each lesson complete as you work through it', ok: st.lessons_done === st.lessons_total },
    { t: `Knowledge quiz (${st.quiz ? st.quiz.score + '%' : 'not passed'})`, s: `Pass mark ${st.standards.quiz_pass}%`, ok: st.quiz_passed },
    { t: `Scenario test (${st.scenario ? st.scenario.score + '%' : 'not passed'})`, s: `Pass mark ${st.standards.scenario_pass}%`, ok: st.scenario_passed },
    { t: `Practical (${st.practical ? (st.practical.average != null ? st.practical.average + '/4' : 'pending') : 'not submitted'})`, s: 'Reviewed against four criteria', ok: st.practical_passed },
  ];
  const history = [];
  if (p.diagnostic) history.push({ name: 'Business Check-Up', kind: 'diagnostic', score: p.diagnostic.overall, passed: null, at: p.diagnostic.created_at });
  p.attempts.forEach(a => history.push({ name: a.kind === 'quiz' ? 'Knowledge quiz' : 'Scenario test', kind: a.kind, score: a.score, passed: a.passed, at: a.created_at }));
  if (st.practical) history.push({ name: 'Practical assignment', kind: 'practical', score: st.practical.average != null ? st.practical.average + '/4' : '—', passed: st.practical.status === 'reviewed' ? st.practical.passed : null, at: st.practical.reviewed_at || st.practical.created_at, pending: st.practical.status === 'pending' });
  history.sort((a, b) => new Date(b.at) - new Date(a.at));

  mount(`
    <div class="section-head" style="margin-top:0">
      <div><div class="eyebrow">My Business Progress</div><h1>Your record, honestly kept.</h1>
      <p>Every score below comes from a stored assessment attempt or a reviewed practical. Unassessed areas are labelled, not guessed.</p></div>
      <a class="btn btn-outline btn-sm" href="#/test">${icon('test', 13)} Go to assessments</a>
    </div>

    <div class="section">
      <div class="section-head"><div><h2>Five business aspects</h2><p>Your check-up grouped the way owners think about the business. Scores are self-assessed; a verified badge only appears where a module has been fully passed.</p></div></div>
      <div class="aspect-grid">
        ${ASPECTS.map((a) => {
          const s = aspectSummary(p, a);
          return `<div class="stat">
            <div class="k">${esc(a.label)}</div>
            <div class="v">${s.score != null ? s.score : '—'}<small>${s.score != null ? '%' : ''}</small></div>
            <div class="s">${s.score != null ? 'Self-assessed baseline' : 'Not assessed yet'}</div>
            <div style="margin-top:9px">${bar(s.score == null ? 0 : s.score)}</div>
            <p class="tiny muted" style="margin:8px 0 0;line-height:1.45">${esc(a.blurb)}</p>
            ${s.verified ? `<div style="margin-top:8px"><span class="chip chip-teal" style="font-size:9.5px;padding:2px 7px">${s.verified}/${s.total} verified</span></div>` : ''}
          </div>`;
        }).join('')}
      </div>
      <p class="tiny muted" style="margin-top:10px">Legal &amp; Risk is not part of these five owner-facing aspects; it is tracked in the detailed breakdown below.</p>
    </div>

    <div class="split">
      <div>
        <div class="card card-pad">
          <div class="row-between wrap" style="gap:20px">
            <div class="row" style="gap:20px">
              ${ring(p.overall_percent, 112, 9, 'overall', true)}
              <div>
                <div class="eyebrow" style="margin-bottom:4px">Current mastery</div>
                <h2 style="font-size:26px;margin-bottom:6px">${esc(p.mastery.level)}</h2>
                <p class="small muted" style="margin:0">${esc(p.mastery.basis)}</p>
                <div class="row wrap" style="gap:6px;margin-top:10px">
                  <span class="chip chip-navy">${st.passed ? '1 module passed' : '0 modules passed'}</span>
                  <span class="chip chip-grey">${p.attempts.length} scored attempts</span>
                </div>
              </div>
            </div>
            <div style="min-width:190px">
              <div class="level-labels" style="margin-bottom:6px"><span>Beginner</span><span>Optimising</span></div>
              <div class="level-scale">
                ${levels.map((l, i) => `<span class="${levelIdx >= i && levelIdx >= 0 ? 'on' : ''}" style="background:${levelIdx >= i && levelIdx >= 0 ? 'var(--teal)' : '#E8EEF4'}"></span>`).join('')}
              </div>
              <p class="tiny muted" style="margin-top:8px">Beginner → Developing → Structured → Optimising, based on verified evidence.</p>
            </div>
          </div>
        </div>

        <div class="grid auto-220" style="margin-top:16px">
          <div class="stat"><div class="k">Diagnostic</div><div class="v">${p.diagnostic ? p.diagnostic.overall : '—'}<small>${p.diagnostic ? '%' : ''}</small></div><div class="s">${p.diagnostic ? fmtDate(p.diagnostic.created_at) : 'Not taken yet'}</div></div>
          <div class="stat"><div class="k">Module progress</div><div class="v">${st.percent}<small>%</small></div><div class="s">${st.lessons_done}/${st.lessons_total} lessons · ${[st.quiz_passed, st.scenario_passed, st.practical_passed].filter(Boolean).length}/3 criteria</div></div>
          <div class="stat"><div class="k">Action plan</div><div class="v">${p.plan_done}<small>/${p.plan.length}</small></div><div class="s">Steps marked complete</div></div>
        </div>
      </div>

      <div class="level-card">
        <div class="eyebrow" style="color:var(--sun)">Mastery rules</div>
        <h3 style="font-size:18px;margin-bottom:8px">No level without evidence</h3>
        <p style="margin-bottom:12px">Levels are never assigned from confidence, logins or unfinished work.</p>
        <div class="small" style="color:#D3E4F1;line-height:1.75">
          <div><b style="color:#fff">Beginner</b> — check-up complete, no module assessment passed.</div>
          <div><b style="color:#fff">Developing</b> — at least one scored assessment passed.</div>
          <div><b style="color:#fff">Structured</b> — full module verified: quiz, scenario and reviewed practical.</div>
          <div><b style="color:#fff">Optimising</b> — module verified with quiz ≥ 90%, practical ≥ 3.5/4 and two plan items completed.</div>
        </div>
        <div style="margin-top:14px;padding-top:12px;border-top:1px solid rgba(255,255,255,.14)" class="tiny">
          <span style="color:#9FBDD5">Components without a scored assessment show “Not assessed”.</span>
        </div>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><div><h2>Detailed breakdown</h2><p>All eight components, including Legal &amp; Risk: diagnostic score, verified module status and mastery level.</p></div></div>
      <div class="card"><div class="table-wrap"><table class="table">
        <thead><tr><th>Component</th><th>Diagnostic</th><th>Module</th><th>Mastery</th><th>Source</th><th></th></tr></thead>
        <tbody>
          ${p.components.map((c, i) => `<tr>
            <td class="comp-name"><div class="row" style="gap:9px"><span class="swatch">${String(i + 1).padStart(2, '0')}</span><b>${esc(c.name)}</b></div></td>
            <td style="min-width:120px">${c.score != null ? `<div class="row" style="gap:8px">${bar(c.score)}<span class="small strong">${c.score}%</span></div>` : '<span class="tiny muted">—</span>'}</td>
            <td>${c.id === 'strategy' ? (st.passed ? '<span class="chip chip-teal">Passed</span>' : '<span class="chip chip-yellow">In progress</span>') : '<span class="chip chip-grey">Next release</span>'}</td>
            <td>${pill(c.mastery)}</td>
            <td class="tiny muted">${esc(c.source || '—')}</td>
            <td>${c.id === 'strategy' ? `<a class="link-arrow" href="#/learn/strategy">Open ${icon('right', 12)}</a>` : ''}</td>
          </tr>`).join('')}
        </tbody>
      </table></div></div>
    </div>

    <div class="section split">
      <div class="card card-pad">
        <div class="card-head"><div><h2>Module criteria</h2><p>The four requirements for this module. Profile and diagnostic are baseline steps, tracked above.</p></div><span class="chip ${st.passed ? 'chip-teal' : 'chip-yellow'}">${st.passed ? 'Complete' : 'In progress'}</span></div>
        <div class="checklist">
          ${criteria.map(c => `<div class="checklist-row ${c.ok ? 'done' : ''}">
            <span class="tick">${c.ok ? icon('check', 11) : ''}</span>
            <div class="txt">${esc(c.t)}<span>${esc(c.s)}</span></div>
            <span class="st">${c.ok ? 'Verified' : 'Pending'}</span>
          </div>`).join('')}
        </div>
        <p class="tiny muted" style="margin-top:12px">Mastery is assigned only after a module's quiz, scenario and practical are verified. Diagnostic scores are shown as a baseline, not as a mastery level.</p>
      </div>
      <div class="card card-pad">
        <div class="card-head"><div><h2>Recommended next steps</h2></div></div>
        ${p.next_steps.map((s, i) => `<a class="action-item" href="#/${s.route}"><span class="num">${String(i + 1).padStart(2, '0')}</span>
          <span class="txt"><b>${esc(s.title)}</b><span>${esc(s.detail)}</span></span><span class="go">${icon('right', 14)}</span></a>`).join('')}
        ${p.next_steps.length === 0 ? `<div class="empty" style="padding:14px 0">All current steps complete.</div>` : ''}
      </div>
    </div>

    <div class="section card card-pad">
      <div class="card-head"><div><h2>Personal business improvement plan</h2><p>Specific actions you can finish. Adding and completing actions updates this list.</p></div>
        <span class="chip chip-grey">${p.plan_done}/${p.plan.length} complete</span></div>
      ${p.plan.map(it => `<div class="plan-item ${it.done ? 'done' : ''}">
        <button class="plan-check" type="button" data-action="plan-toggle" data-id="${it.id}" data-done="${it.done ? 1 : 0}" aria-label="${it.done ? 'Mark incomplete' : 'Mark complete'}">${it.done ? icon('check', 12) : ''}</button>
        <div class="pt"><b>${esc(it.title)}</b>${it.detail ? `<p>${esc(it.detail)}</p>` : ''}${it.due ? `<span class="due">${icon('calendar', 11)} Target ${fmtDate(it.due)}</span>` : ''}</div>
        <button class="plan-del" type="button" data-action="plan-delete" data-id="${it.id}" title="Remove action">${icon('trash', 14)}</button>
      </div>`).join('')}
      ${p.plan.length === 0 ? `<div class="empty" style="padding:16px 0">No actions yet. Add your first practical step below.</div>` : ''}
      <form class="inline-form" data-form="plan-add">
        <input class="input" name="title" placeholder="Add an action, e.g. Call five offices about lunch accounts" required maxlength="200">
        <input class="input" name="due" type="date" aria-label="Target date">
        <button class="btn btn-primary" type="submit">${icon('plus', 14)} Add</button>
      </form>
      <p class="tiny muted" style="margin-top:8px">Actions are private to your account. Completing them contributes to the “Optimising” level only when combined with verified assessment results.</p>
    </div>

    <div class="section card card-pad">
      <div class="card-head"><div><h2>Assessment history</h2><p>Every attempt is kept; the best passed result counts toward mastery.</p></div></div>
      ${history.length ? `<div class="table-wrap"><table class="table">
        <thead><tr><th>Assessment</th><th>Date</th><th class="num">Score</th><th>Result</th></tr></thead>
        <tbody>${history.map(h => `<tr>
          <td><b>${esc(h.name)}</b></td>
          <td>${fmtDateTime(h.at)}</td>
          <td class="num">${esc(h.score)}${typeof h.score === 'number' ? '%' : ''}</td>
          <td>${h.pending ? '<span class="chip chip-yellow">Awaiting review</span>' : h.passed === null ? '<span class="chip chip-grey">Baseline</span>' : h.passed ? '<span class="chip chip-teal">Passed</span>' : '<span class="chip chip-red">Not passed</span>'}</td>
        </tr>`).join('')}</tbody>
      </table></div>` : `<div class="empty">No attempts yet.</div>`}
    </div>`, my);
}

/* ------------------------------------------------------------------ coach */
function mdLite(text) {
  let safe = esc(text);
  safe = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  const blocks = safe.split(/\n{2,}/);
  return blocks.map(block => {
    const lines = block.split('\n').filter(l => l.trim() !== '');
    if (lines.length && lines.every(l => /^[•\-]\s+/.test(l.trim()))) {
      return '<ul>' + lines.map(l => `<li>${l.replace(/^[•\-]\s+/, '')}</li>`).join('') + '</ul>';
    }
    if (lines.length && lines.every(l => /^\d+\.\s+/.test(l.trim()))) {
      return '<ol>' + lines.map(l => `<li>${l.replace(/^\d+\.\s+/, '')}</li>`).join('') + '</ol>';
    }
    return '<p>' + lines.join('<br>') + '</p>';
  }).join('');
}

const COACH_SUGGESTIONS = {
  teach: ['Explain break-even in simple terms', 'How do I choose which customer to focus on?', 'Teach me how pricing affects profit'],
  solve: ['My profit is falling even though sales are up', 'My staff keep making the same mistakes', 'Should I discount to win a big order?'],
  test: ['Test me on break-even', 'Ask me a pricing question', 'Quiz me on strategy basics'],
};

const COACH_INTRO = {
  teach: 'Teach Me explains one concept at a time, in plain language, with a small-business example.',
  solve: 'Help Me Solve diagnoses your situation first, then gives numbered steps and the reasoning behind them.',
  test: 'Test My Knowledge asks short questions and explains the answer. For scored attempts, use Test Your Skills.',
};

function renderCoach(my) {
  const c = state.coach;
  const live = state.ai.configured;
  const messages = c.messages;
  mount(`
    <div class="section-head" style="margin-top:0">
      <div><div class="eyebrow">AI Business Coach</div><h1>Think it through, out loud.</h1>
        <p>Ask about a real business problem. The coach explains, asks questions, and suggests practical steps — it will not invent your results.</p></div>
      <span class="top-chip ${live ? '' : 'gold'}"><span class="dot"></span>${live ? 'Live AI connected' : 'Demo mode'}</span>
    </div>
    <div class="coach-layout">
      <div class="card chat-card">
        <div class="chat-head">
          <div class="avatar-bot">${icon('spark', 19)}</div>
          <div style="flex:1"><b>futurePreneur Coach</b><span>${live ? 'Connected through the server-side API key' : 'Scripted demo guidance — no external AI connected'}</span></div>
          <button class="btn btn-ghost btn-sm" type="button" data-action="coach-reset">${icon('refresh', 13)} New chat</button>
        </div>
        <div class="chat-modes" role="tablist" aria-label="Coaching mode">
          ${[['teach', 'Teach Me'], ['solve', 'Help Me Solve'], ['test', 'Test My Knowledge']].map(m => `<button type="button" class="mode-btn ${c.mode === m[0] ? 'on' : ''}" data-action="coach-mode" data-mode="${m[0]}">${m[1]}</button>`).join('')}
          <span class="mode-hint">${esc(COACH_INTRO[c.mode])}</span>
        </div>
        ${!live ? `<div class="chat-demo"><div class="demo-banner">${icon('alert', 16)}
            <div><b>Demo mode.</b> Replies are pre-written coaching scripts, not generated by an AI model. An administrator can connect an API key on the server; the key is never sent to the browser.</div></div></div>` : ''}
        <div class="chat-body" id="chat-body">
          ${messages.length === 0 ? `<div class="bubble"><span class="bsym">AI</span>
            <div class="bcontent"><p><strong>${esc(COACH_INTRO[c.mode].split(' ')[0] === 'Teach' ? 'Let’s learn something useful.' : c.mode === 'solve' ? 'Tell me what is happening.' : 'Let’s check your knowledge.')}</strong></p>
            <p>${esc(COACH_INTRO[c.mode])} Start with a question about your own business — or pick one of the prompts below.</p>
            ${c.mode === 'test' ? `<p><button class="btn btn-teal btn-sm" type="button" data-action="coach-begin-test">Start the first question ${icon('right', 13)}</button></p>` : ''}
            <p class="tiny" style="color:#6B7F92">I will always tell you when I am giving general guidance rather than a verified answer.</p></div></div>` : ''}
          ${messages.map(m => `<div class="bubble ${m.role === 'user' ? 'user' : ''}">
            <span class="bsym">${m.role === 'user' ? esc(initials(state.user.name)) : 'AI'}</span>
            <div class="bcontent">${mdLite(m.content)}</div></div>`).join('')}
          ${c.busy ? `<div class="bubble"><span class="bsym">AI</span><div class="bcontent"><span class="typing"><i></i><i></i><i></i></span></div></div>` : ''}
        </div>
        <div class="chat-compose">
          ${messages.length < 3 ? `<div class="suggestions">${COACH_SUGGESTIONS[c.mode].map(s => `<button type="button" class="suggestion" data-action="coach-suggest" data-text="${esc(s)}">${esc(s)}</button>`).join('')}</div>` : ''}
          <form data-form="coach-send">
            <div class="compose-row">
              <textarea name="message" id="coach-input" rows="1" placeholder="Describe your situation, or ask a business question…" ${c.busy ? 'disabled' : ''}></textarea>
              <button class="send" type="submit" aria-label="Send message" ${c.busy ? 'disabled' : ''}>${icon('send', 17)}</button>
            </div>
            <div class="compose-meta"><span>${live ? 'Live AI · responses may need checking against your numbers' : 'Demo mode · scripted responses, clearly labelled'}</span><span>Enter to send · Shift + Enter for a new line</span></div>
          </form>
        </div>
      </div>
      <aside class="coach-side">
        <div class="card card-pad">
          <h3>Three ways to use it</h3>
          <div style="margin-bottom:10px"><b class="small">Teach Me</b><p style="margin:2px 0 0">Concepts, examples and a next step.</p></div>
          <div style="margin-bottom:10px"><b class="small">Help Me Solve</b><p style="margin:2px 0 0">A structured diagnosis of a live problem.</p></div>
          <div><b class="small">Test My Knowledge</b><p style="margin:2px 0 0">Short questions with explanations. Not a substitute for scored tests.</p></div>
        </div>
        <div class="card card-pad">
          <h3>How this is wired</h3>
          <p>The coach sends your conversation to the server. If an API key is configured there, the server calls the model; the browser never sees the key. Otherwise you get this labelled demo mode.</p>
          <hr class="hr">
          <div class="row" style="gap:7px;color:${live ? 'var(--green)' : '#9A7308'}">${icon(live ? 'check' : 'alert', 14)}<span class="tiny strong">${live ? 'Live model: ' + esc(state.ai.model || 'configured') : 'No API key configured'}</span></div>
          <p class="tiny muted" style="margin-top:6px">${live ? 'Answers are generated by a model; verify numbers before acting.' : 'Demo answers are fixed scripts written for this version. They are not personalised by AI.'}</p>
        </div>
        <div class="card card-pad">
          <h3>Good coaching habit</h3>
          <p class="quote">Bring one number and one decision. “Sales are RM18k, margin is 20%, should I hire?” is easier to help with than “business is hard”.</p>
        </div>
      </aside>
    </div>`, my);
  if (state.coach.messages.length) requestAnimationFrame(scrollChat);
}

function scrollChat() {
  const body = $('#chat-body');
  if (body) body.scrollTop = body.scrollHeight;
}

async function sendCoach(text) {
  if (!text.trim() || state.coach.busy) return;
  state.coach.messages.push({ role: 'user', content: text.trim() });
  state.coach.busy = true;
  renderCoach(begin());
  try {
    const data = await api('/api/coach', {
      method: 'POST',
      body: JSON.stringify({ mode: state.coach.mode, messages: state.coach.messages }),
    });
    state.coach.messages.push({ role: 'assistant', content: data.reply });
    state.coach.busy = false;
    if (data.ai_error) toast('Live AI failed: ' + data.ai_error, 'err');
    renderCoach(begin());
  } catch (err) {
    state.coach.busy = false;
    toast(err.message, 'err');
    renderCoach(begin());
  }
}

/* ------------------------------------------------------------------ admin */
async function viewAdmin(my, sub) {
  if (state.user.role !== 'admin') {
    mount(`<div class="card card-pad"><div class="empty"><div class="icon">${icon('lock', 22)}</div>
      <p class="strong">Administrator access required.</p><p class="small muted">Sign in with the admin account to manage content and review learner work.</p>
      <a class="btn btn-outline btn-sm" href="#/dashboard">Back to dashboard</a></div></div>`, my);
    return;
  }
  const tab = ['learners', 'reviews', 'questions', 'content', 'settings'].includes(sub) ? sub : state.admin.tab;
  state.admin.tab = tab;
  const tabs = `<div class="tabs">
    ${[['learners', 'Learners'], ['reviews', 'Practical reviews'], ['questions', 'Questions'], ['content', 'Content'], ['settings', 'Standards']].map(t =>
      `<button type="button" class="tab ${tab === t[0] ? 'on' : ''}" data-action="admin-tab" data-tab="${t[0]}">${t[1]}</button>`).join('')}
    </div>`;

  if (tab === 'content') {
    await viewAdminContent(my, tabs);
    return;
  }

  if (tab === 'learners') {
    const data = await api('/api/admin/overview');
    if (my !== seq) return;
    mount(`${headAdmin('Platform overview')}${tabs}
      <div class="grid auto-220" style="margin-bottom:18px">
        <div class="stat"><div class="k">Learners</div><div class="v">${data.stats.learners}</div><div class="s">Registered accounts</div></div>
        <div class="stat"><div class="k">Profiles</div><div class="v">${data.stats.profiles}</div><div class="s">Business profiles created</div></div>
        <div class="stat"><div class="k">Check-ups</div><div class="v">${data.stats.diagnostics}</div><div class="s">Diagnostic attempts</div></div>
        <div class="stat"><div class="k">Pending reviews</div><div class="v">${data.stats.pending_reviews}</div><div class="s">Practical submissions</div></div>
      </div>
      <div class="card card-pad">
        <div class="card-head"><div><h2>Learners</h2><p>Live progress calculated from stored attempts and reviews.</p></div></div>
        <div class="table-wrap"><table class="table">
          <thead><tr><th>Learner</th><th>Business</th><th>Check-up</th><th>Overall</th><th>Mastery</th><th>Module</th><th>Practical</th></tr></thead>
          <tbody>${data.learners.map(l => `<tr>
            <td><b>${esc(l.name)}</b><div class="tiny muted">${esc(l.email)}</div></td>
            <td>${esc(l.business_name || '—')}<div class="tiny muted">${esc(l.sector || '')}</div></td>
            <td>${l.diagnostic != null ? l.diagnostic + '%' : '—'}</td>
            <td style="min-width:120px"><div class="row" style="gap:8px">${bar(l.overall_percent)}<span class="small strong">${l.overall_percent}%</span></div></td>
            <td>${pill(l.mastery)}</td>
            <td>${l.module_passed ? '<span class="chip chip-teal">Passed</span>' : '<span class="chip chip-grey">In progress</span>'}</td>
            <td>${l.practical_status === 'pending' ? '<span class="chip chip-yellow">Pending</span>' : l.practical_status === 'reviewed' ? '<span class="chip chip-grey">Reviewed</span>' : '<span class="tiny muted">—</span>'}</td>
          </tr>`).join('')}</tbody>
        </table></div>
      </div>`, my);
    return;
  }

  if (tab === 'reviews') {
    const data = await api('/api/admin/submissions');
    if (my !== seq) return;
    mount(`${headAdmin('Practical reviews')}${tabs}
      <p class="small muted" style="margin:-8px 0 16px">Reviewing sets the rubric result. Passing requires an average of ${data.standards.rubric_min}/4 with no criterion below ${data.standards.rubric_floor}. Only a reviewer can mark the practical passed.</p>
      ${data.submissions.length === 0 ? `<div class="card"><div class="empty">No practical submissions yet.</div></div>` : ''}
      ${data.submissions.map(s => `<div class="review-card ${s.status}" data-sub="${s.id}">
        <div class="row-between wrap" style="gap:10px;margin-bottom:10px">
          <div class="row" style="gap:10px"><div class="avatar" style="background:#E9EFF6;color:#16406A">${esc(initials(s.learner))}</div>
            <div><b class="small">${esc(s.learner)}</b><div class="tiny muted">${esc(s.email)} · submitted ${fmtDate(s.created_at)}</div></div></div>
          <span class="chip ${s.status === 'reviewed' ? (s.passed ? 'chip-teal' : 'chip-red') : 'chip-yellow'}">${s.status === 'reviewed' ? (s.passed ? 'Passed · ' + s.average + '/4' : 'Not passed · ' + s.average + '/4') : 'Awaiting review'}</span>
        </div>
        <details ${s.status === 'pending' ? 'open' : ''}>
          <summary class="small strong" style="cursor:pointer;color:var(--navy-700)">View submission and rubric</summary>
          <div style="margin-top:12px">
            ${data.prompts.map((pr, i) => `<div class="answer-block"><div class="k">${i + 1}. ${esc(pr.label)}</div><div class="v">${esc(s.responses[pr.id] || '—')}</div></div>`).join('')}
            <div class="rubric-grid">
              ${data.criteria.map(c => `<label>${esc(c.label)}<span>${esc(c.hint)}</span></label>
                <select class="select" data-crit="${c.id}" aria-label="${esc(c.label)}">
                  ${[0, 1, 2, 3, 4].map(n => `<option value="${n}" ${s.rubric && s.rubric[c.id] === n ? 'selected' : (!s.rubric && n === 3 ? 'selected' : '')}>${n} / 4</option>`).join('')}
                </select>`).join('')}
            </div>
            <div class="field" style="margin-top:12px"><label>Reviewer note (visible to the learner)</label>
              <textarea class="textarea" data-note style="min-height:70px" placeholder="What was strong, what needs revision…">${esc(s.reviewer_note || '')}</textarea></div>
            <button class="btn btn-primary btn-sm" type="button" data-action="admin-review" data-id="${s.id}">${icon('check', 13)} Save review</button>
          </div>
        </details>
      </div>`).join('')}`, my);
    return;
  }

  if (tab === 'questions') {
    const data = await api('/api/admin/questions');
    if (my !== seq) return;
    const editing = state.admin.editing;
    const filtered = data.questions.filter(q => state.admin.qkind === 'all' || q.kind === state.admin.qkind);
    const showForm = state.admin.showForm || !!editing;
    mount(`${headAdmin('Assessment questions')}${tabs}
      <div class="row-between wrap" style="gap:10px;margin-bottom:14px">
        <div class="row wrap" style="gap:5px">
          ${['all', 'diagnostic', 'quiz', 'scenario'].map(k => `<button class="chip ${state.admin.qkind === k ? 'chip-navy' : 'chip-grey'}" type="button" data-action="admin-qfilter" data-kind="${k}">${k === 'all' ? 'All' : k[0].toUpperCase() + k.slice(1)} <span style="opacity:.6">${k === 'all' ? data.questions.length : data.questions.filter(q => q.kind === k).length}</span></button>`).join('')}
        </div>
        <button class="btn btn-primary btn-sm" type="button" data-action="admin-qnew">${icon('plus', 13)} Add question</button>
      </div>
      ${showForm ? `<form class="admin-question-form" data-form="question-save">
        <div class="row-between" style="margin-bottom:12px"><h3>${editing ? 'Edit question' : 'New question'}</h3>
          <button type="button" class="btn btn-ghost btn-sm" data-action="admin-qcancel">${icon('close', 13)} Cancel</button></div>
        <div class="field-row">
          <div class="field"><label>Assessment type</label><select class="select" name="kind">
            ${['diagnostic', 'quiz', 'scenario'].map(k => `<option value="${k}" ${editing && editing.kind === k ? 'selected' : ''}>${k}</option>`).join('')}</select></div>
          <div class="field"><label>Component</label><select class="select" name="component">
            ${data.components.map(c => `<option value="${c.id}" ${editing && editing.component === c.id ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select></div>
        </div>
        <div class="field"><label>Topic</label><input class="input" name="topic" value="${esc(editing ? editing.topic : '')}" placeholder="e.g. Break-even" required></div>
        <div class="field"><label>Question</label><textarea class="textarea" name="prompt" required>${esc(editing ? editing.prompt : '')}</textarea></div>
        <div class="field"><label>Options — one per line (2–6)</label><textarea class="textarea" name="options" required placeholder="Option A&#10;Option B&#10;Option C">${esc(editing ? editing.options.join('\n') : '')}</textarea></div>
        <div class="field-row">
          <div class="field"><label>Correct option</label><select class="select" name="correct">
            ${[0, 1, 2, 3, 4, 5].map(i => `<option value="${i}" ${editing && editing.correct === i ? 'selected' : ''}>Option ${'ABCDEF'[i]}</option>`).join('')}</select>
            <div class="hint">Positions beyond the number of options are rejected by the server.</div></div>
          <div class="field"><label>Explanation</label><input class="input" name="explanation" value="${esc(editing ? editing.explanation : '')}" placeholder="Why the answer is correct" required></div>
        </div>
        <label class="checkbox" style="margin-bottom:12px"><input type="checkbox" name="active" ${!editing || editing.active ? 'checked' : ''}> Active (included in assessments)</label>
        <button class="btn btn-primary btn-sm" type="submit">${icon('check', 13)} ${editing ? 'Save changes' : 'Create question'}</button>
      </form>` : ''}
      ${filtered.map(q => `<div class="q-row">
        <div class="row-between" style="gap:10px"><div class="qt">${esc(q.prompt)}</div>
          <div class="q-actions"><button class="btn btn-ghost btn-sm" type="button" data-action="admin-qedit" data-id="${esc(q.id)}">${icon('edit', 12)} Edit</button>
          <button class="btn btn-ghost btn-sm" type="button" data-action="admin-qdelete" data-id="${esc(q.id)}">${icon('trash', 12)}</button></div></div>
        <div class="qm"><span class="chip chip-grey">${esc(q.kind)}</span><span>${esc(compName(q.component))}</span><span>· ${esc(q.topic)}</span>${q.active ? '' : '<span class="chip chip-red">Inactive</span>'}</div>
        <div class="qa">✓ ${esc(q.options[q.correct])}</div>
      </div>`).join('')}
      ${filtered.length === 0 ? `<div class="card"><div class="empty">No questions of this type.</div></div>` : ''}`, my);
    return;
  }

  mount(`${headAdmin('Standards')}${tabs}
    <div class="split">
      <div class="card card-pad">
        <div class="card-head"><div><h2>Passing criteria</h2><p>Applied immediately to new submissions and reviews.</p></div></div>
        <form data-form="admin-settings">
          <div class="field-row">
            <div class="field"><label for="quiz_pass">Knowledge quiz pass mark (%)</label>
              <input class="input" id="quiz_pass" name="quiz_pass" type="number" min="0" max="100" value="${state.settings.quiz_pass}" required></div>
            <div class="field"><label for="scenario_pass">Scenario test pass mark (%)</label>
              <input class="input" id="scenario_pass" name="scenario_pass" type="number" min="0" max="100" value="${state.settings.scenario_pass}" required></div>
          </div>
          <div class="field-row">
            <div class="field"><label for="rubric_min">Practical average required (/4)</label>
              <input class="input" id="rubric_min" name="rubric_min" type="number" min="0" max="4" step="0.25" value="${state.settings.rubric_min}" required></div>
            <div class="field"><label for="rubric_floor">Minimum per criterion (/4)</label>
              <input class="input" id="rubric_floor" name="rubric_floor" type="number" min="0" max="4" step="1" value="${state.settings.rubric_floor}" required></div>
          </div>
          <button class="btn btn-primary btn-sm" type="submit">${icon('check', 13)} Save standards</button>
          <p class="tiny muted" style="margin-top:9px">Changing standards does not retroactively alter completed reviews or attempts; it applies to future scoring.</p>
        </form>
      </div>
      <div class="card card-pad">
        <h3 style="margin-bottom:6px">Accounts</h3>
        <p class="small muted">Current administrator: <b>${esc(state.user.email)}</b>. Learner accounts and progress are managed through the API and database; no passwords are exposed here.</p>
        <hr class="hr">
        <h3 style="margin-bottom:8px">AI coach</h3>
        <div class="row" style="gap:8px">${icon(state.ai.configured ? 'check' : 'alert', 15)}
          <span class="small">${state.ai.configured ? 'Live API configured on the server.' : 'Demo mode — no API key configured.'}</span></div>
        <p class="tiny muted" style="margin-top:7px">Set <code>BIZREADY_AI_KEY</code> in the server environment, or add <code>ai.api_key</code> to <code>config.json</code>. Keys never reach the browser.</p>
      </div>
    </div>`, my);
}

function moduleEditorHTML(module, lesson, template, revisions) {
  const statusChip = module.status === 'published'
    ? '<span class="chip chip-teal">Published</span>'
    : '<span class="chip chip-yellow">Draft</span>';
  return `
    <div class="card card-pad">
      <div class="row-between wrap" style="gap:10px">
        <div><h2 style="margin-bottom:4px">${esc(module.title)}</h2>
          <div class="tiny muted">${esc(module.component)} · v${module.version} · updated ${fmtDate(module.updated_at)}</div></div>
        <div class="row wrap" style="gap:8px">
          ${statusChip}
          <button class="btn btn-ghost btn-sm" type="button" data-action="admin-preview">${state.admin.preview ? 'Hide preview' : 'Preview'}</button>
          <button class="btn ${module.status === 'published' ? 'btn-outline' : 'btn-primary'} btn-sm" type="button" data-action="admin-module-status" data-status="${module.status === 'published' ? 'draft' : 'published'}">
            ${module.status === 'published' ? 'Unpublish' : 'Publish'}</button>
        </div>
      </div>
      ${state.admin.preview ? `<div class="preview-pane">
        <div class="eyebrow">Learner preview · draft-safe</div>
        <h3 style="margin:6px 0">${esc(module.title)}</h3>
        <p class="small muted">${esc(module.tagline)}</p>
        <p class="small"><b>Outcome:</b> ${esc(module.outcome)}</p>
        <ol class="tiny" style="margin:10px 0 0 18px">${module.lessons.map(l => `<li><b>${esc(l.title)}</b> — ${esc(l.summary)}</li>`).join('')}</ol>
      </div>` : ''}
    </div>

    <div class="card card-pad" style="margin-top:16px">
      <div class="card-head"><div><h2>Module details</h2><p>Shown at the top of the learner module page.</p></div></div>
      <form data-form="module-meta">
        <div class="field-row">
          <div class="field"><label>Title</label><input class="input" name="title" value="${esc(module.title)}" required maxlength="120"></div>
          <div class="field"><label>Level</label><select class="select" name="level">
            ${['Foundation', 'Practical', 'Advanced'].map(l => `<option ${module.level === l ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
        </div>
        <div class="field"><label>Tagline</label><input class="input" name="tagline" value="${esc(module.tagline)}" maxlength="300"></div>
        <div class="field-row">
          <div class="field"><label>Typical time</label><input class="input" name="hours" value="${esc(module.hours)}" placeholder="45–60 min"></div>
          <div class="field"><label>Outcome</label><input class="input" name="outcome" value="${esc(module.outcome)}"></div>
        </div>
        <div class="field"><label>Intro paragraphs (blank line between)</label>
          <textarea class="textarea" name="intro" rows="4">${esc((module.intro || []).join('\n\n'))}</textarea></div>
        <button class="btn btn-primary btn-sm" type="submit">Save module details</button>
      </form>
    </div>

    <div class="card card-pad" style="margin-top:16px">
      <div class="card-head"><div><h2>Practical assignment</h2><p>Reviewed by an admin against the rubric. Required before publishing.</p></div></div>
      <form data-form="practical-save">
        <div class="field"><label>Title</label><input class="input" name="practical_title" value="${esc((module.practical || {}).title || '')}" required></div>
        <div class="field"><label>Intro</label><textarea class="textarea" name="practical_intro" rows="2">${esc((module.practical || {}).intro || '')}</textarea></div>
        <div class="field"><label>Criteria — one per line: <code>id | Label | Hint</code></label>
          <textarea class="textarea" name="criteria" rows="4" placeholder="customer_clarity | Customer clarity | One primary customer group">${esc(((module.practical || {}).criteria || []).map(c => `${c.id} | ${c.label} | ${c.hint}`).join('\n'))}</textarea></div>
        <div class="field"><label>Prompts — one per line: <code>id | criterion | Question | Placeholder</code></label>
          <textarea class="textarea" name="prompts" rows="4" placeholder="p1 | customer_clarity | Who is your customer? | Be specific">${esc(((module.practical || {}).prompts || []).map(p => `${p.id} | ${p.criterion} | ${p.label} | ${p.placeholder || ''}`).join('\n'))}</textarea></div>
        <button class="btn btn-primary btn-sm" type="submit">Save practical</button>
      </form>
    </div>

    <div class="card card-pad" style="margin-top:16px">
      <div class="card-head"><div><h2>Lessons</h2><p>${module.lessons.length} lesson${module.lessons.length === 1 ? '' : 's'} · edit the text learners read.</p></div>
        <button class="btn btn-ghost btn-sm" type="button" data-action="admin-lesson-new">+ Add lesson</button></div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px">
        ${module.lessons.map(l => `<button type="button" class="chip ${lesson && l.id === lesson.id ? 'chip-navy' : 'chip-grey'}" data-action="admin-lesson-select" data-id="${esc(l.id)}">${l.number}. ${esc(l.title)}</button>`).join('')}
      </div>
      ${lesson ? `<form data-form="lesson-save">
        <input type="hidden" name="lesson_id" value="${esc(lesson.id)}">
        <div class="field-row">
          <div class="field"><label>Lesson title</label><input class="input" name="title" value="${esc(lesson.title)}" required maxlength="160"></div>
          <div class="field"><label>Minutes</label><input class="input" name="minutes" type="number" min="1" max="180" value="${lesson.minutes}" required></div>
        </div>
        <div class="field"><label>Summary</label><input class="input" name="summary" value="${esc(lesson.summary)}" required maxlength="500"></div>
        <div class="field"><label>Explanation (blank line between paragraphs)</label>
          <textarea class="textarea" name="explanation" rows="7" required>${esc((lesson.explanation || []).join('\n\n'))}</textarea></div>
        <div class="field-row">
          <div class="field"><label>Example title</label><input class="input" name="example_title" value="${esc((lesson.example || {}).title || '')}"></div>
          <div class="field"><label>Example text</label><textarea class="textarea" name="example_text" rows="3">${esc((lesson.example || {}).text || '')}</textarea></div>
        </div>
        <div class="field"><label>What to do (one per line)</label><textarea class="textarea" name="do" rows="4">${esc((lesson.do || []).join('\n'))}</textarea></div>
        <div class="field"><label>What not to do (one per line)</label><textarea class="textarea" name="dont" rows="4">${esc((lesson.dont || []).join('\n'))}</textarea></div>
        <div class="field"><label>Why it matters</label><textarea class="textarea" name="why" rows="3">${esc(lesson.why || '')}</textarea></div>
        <div class="field"><label>Common mistakes (one per line)</label><textarea class="textarea" name="mistakes" rows="4">${esc((lesson.mistakes || []).join('\n'))}</textarea></div>
        <div class="field-row">
          <div class="field"><label>Exercise prompt</label><textarea class="textarea" name="exercise_prompt" rows="2">${esc((lesson.exercise || {}).prompt || '')}</textarea></div>
          <div class="field"><label>Exercise steps (one per line)</label><textarea class="textarea" name="exercise_steps" rows="4">${esc(((lesson.exercise || {}).steps || []).join('\n'))}</textarea></div>
        </div>
        <div class="row" style="gap:8px">
          <button class="btn btn-primary btn-sm" type="submit">Save lesson</button>
          <button class="btn btn-ghost btn-sm" type="button" data-action="admin-lesson-delete" data-id="${esc(lesson.id)}">Delete lesson</button>
          <span class="tiny muted">Revision history keeps every save.</span>
        </div>
      </form>` : '<div class="empty">Add a lesson to start authoring this module.</div>'}
    </div>

    <div class="card card-pad" style="margin-top:16px">
      <div class="card-head"><div><h2>Templates</h2><p>Downloadable files attached to this module. To serve your own file, drop it in <code>content/templates/&lt;slug&gt;.&lt;ext&gt;</code>; any file in <code>content/templates/&lt;module-id&gt;/</code> is added automatically.</p></div>
        <button class="btn btn-ghost btn-sm" type="button" data-action="admin-template-new">+ New template</button></div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px">
        ${module.templates.map(t => `<button type="button" class="chip ${template && t.slug === template.slug ? 'chip-navy' : 'chip-grey'}" data-action="admin-template-select" data-slug="${esc(t.slug)}">${esc(t.title)}</button>`).join('')}
      </div>
      ${state.admin.newTemplate || template ? `<form data-form="template-save">
        <div class="field-row">
          <div class="field"><label>Slug (lowercase, dashes)</label><input class="input" name="slug" value="${esc(template ? template.slug : '')}" ${template ? 'readonly' : ''} required></div>
          <div class="field"><label>File name</label><input class="input" name="filename" value="${esc(template ? template.filename : '')}" placeholder="futurepreneur-template.md" required></div>
        </div>
        <div class="field"><label>Title</label><input class="input" name="title" value="${esc(template ? template.title : '')}" required></div>
        <div class="field"><label>Description</label><input class="input" name="description" value="${esc(template ? template.description : '')}"></div>
        <div class="field"><label>Body (plain text, Markdown or CSV)</label><textarea class="textarea" name="body" rows="8">${esc(template ? template.body : '')}</textarea></div>
        <div class="row" style="gap:8px"><button class="btn btn-primary btn-sm" type="submit">Save template</button>
          ${template ? `<button class="btn btn-ghost btn-sm" type="button" data-action="admin-template-delete" data-slug="${esc(template.slug)}">Delete</button>` : ''}</div>
      </form>` : '<div class="tiny muted">Select a template to edit, or create one.</div>'}
    </div>

    <div class="card card-pad" style="margin-top:16px">
      <div class="card-head"><div><h2>Revision history</h2><p>Last edits to this module, newest first.</p></div></div>
      ${revisions.length ? `<div class="table-wrap"><table class="table"><thead><tr><th>When</th><th>Action</th><th>Editor</th><th>Snapshot</th></tr></thead><tbody>
        ${revisions.map(r => `<tr><td class="tiny">${fmtDateTime(r.created_at)}</td><td><span class="chip chip-grey">${esc(r.action)}</span></td>
          <td class="tiny">${esc(r.editor || 'system')}</td><td class="tiny muted">v${r.snapshot.version || '—'} · ${esc(r.snapshot.status || '')}</td></tr>`).join('')}
      </tbody></table></div>` : '<div class="empty">No edits yet. Saving a module or lesson records a revision.</div>'}
    </div>`;
}

async function viewAdminContent(my, tabs) {
  const list = await api('/api/admin/modules');
  if (my !== seq) return;
  if (!state.admin.moduleId || !list.modules.some(m => m.id === state.admin.moduleId)) {
    state.admin.moduleId = list.modules.length ? list.modules[0].id : null;
  }
  let detail = null;
  if (state.admin.moduleId) {
    detail = await api('/api/admin/modules/' + encodeURIComponent(state.admin.moduleId));
    if (my !== seq) return;
  }
  const module = detail ? detail.module : null;
  const lesson = module ? (module.lessons.find(l => l.id === state.admin.lesson) || module.lessons[0]) : null;
  const template = module && !state.admin.newTemplate
    ? (module.templates.find(t => t.slug === state.admin.template) || module.templates[0] || null)
    : null;

  mount(`${headAdmin('Content')}${tabs}
    <div class="admin-split">
      <div class="card card-pad">
        <div class="card-head"><div><h2>Modules</h2><p>${list.modules.length} total</p></div></div>
        <div style="display:grid;gap:8px">
          ${list.modules.map(m => `<button type="button" class="module-pick ${m.id === state.admin.moduleId ? 'on' : ''}" data-action="admin-module-select" data-id="${esc(m.id)}">
            <span class="row-between" style="gap:6px;align-items:flex-start"><b>${esc(m.title)}</b><em class="chip ${m.status === 'published' ? 'chip-teal' : 'chip-yellow'}">${m.status}</em></span>
            <span>${m.lessons} lessons · ${m.quiz} quiz · ${m.scenario} scenario</span>
          </button>`).join('')}
        </div>
        <hr class="hr">
        ${state.admin.newModule ? `<form data-form="module-new">
          <div class="field"><label>Module id</label><input class="input" name="id" placeholder="marketing-basics" required></div>
          <div class="field"><label>Component</label><select class="select" name="component">
            ${list.components.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div>
          <div class="field"><label>Title</label><input class="input" name="title" placeholder="Marketing Foundations" required></div>
          <div class="row" style="gap:6px"><button class="btn btn-primary btn-sm" type="submit">Create draft</button>
            <button class="btn btn-ghost btn-sm" type="button" data-action="admin-module-new">Cancel</button></div>
        </form>` : `<button class="btn btn-outline btn-sm" type="button" data-action="admin-module-new">+ New module</button>`}
        <p class="tiny muted" style="margin-top:12px">New modules start as drafts. Publish requires at least one lesson, 5 quiz questions, 3 scenario questions and a practical.</p>
      </div>
      <div>${module ? moduleEditorHTML(module, lesson, template, detail.revisions || []) : `<div class="card card-pad"><div class="empty">No modules yet.</div></div>`}</div>
    </div>`, my);
}

function headAdmin(title) {
  return `<div class="section-head" style="margin-top:0"><div><div class="eyebrow">Admin</div><h1>${esc(title)}</h1>
    <p>Manage content, standards and learner progress. Changes take effect immediately.</p></div></div>`;
}

/* ------------------------------------------------------------------ events */
document.addEventListener('click', async (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) {
    const anchor = e.target.closest('.sidebar a');
    if (anchor) closeSidebar();
    return;
  }
  const action = el.dataset.action;
  if (action === 'open-menu') { $('#sidebar').classList.add('open'); $('#backdrop').classList.add('show'); return; }
  if (action === 'close-menu') { closeSidebar(); return; }
  if (action === 'reload') { router(); return; }
  if (action === 'logout') {
    try { await api('/api/auth/logout', { method: 'POST' }); } catch (_) {}
    state.user = null; state.progress = null; state.checkupResult = null; state.runner = null;
    state.assessmentResult = null; state.coach.messages = []; lastRoute = '';
    location.hash = '';
    renderAuth();
    return;
  }
  if (action === 'auth-mode') { state.authMode = el.dataset.mode; state.authError = ''; renderAuth(); return; }
  if (action === 'demo-login') { doLogin(el.dataset.email, el.dataset.password); return; }
  if (action === 'edit-profile') { state.editProfile = true; viewCheckup(begin()); return; }
  if (action === 'cancel-profile') { state.editProfile = false; viewCheckup(begin()); return; }
  if (action === 'start-checkup') { state.editProfile = false; startCheckup(); return; }
  if (action === 'retake-checkup') { startCheckup(); return; }
  if (action === 'exit-runner') {
    const was = state.runner ? state.runner.type : null;
    state.runner = null;
    if (was === 'checkup') viewCheckup(begin()); else viewTest(begin(), '');
    return;
  }
  if (action === 'answer') {
    if (!state.runner) return;
    const q = state.runner.questions[state.runner.index];
    state.runner.answers[q.id] = Number(el.dataset.i);
    renderRunner();
    return;
  }
  if (action === 'runner-next') {
    if (!state.runner) return;
    const q = state.runner.questions[state.runner.index];
    if (state.runner.answers[q.id] === undefined) { toast('Choose an answer to continue.'); return; }
    state.runner.index = Math.min(state.runner.index + 1, state.runner.questions.length - 1);
    renderRunner();
    return;
  }
  if (action === 'runner-back') { if (!state.runner) return; state.runner.index = Math.max(0, state.runner.index - 1); renderRunner(); return; }
  if (action === 'runner-submit') { submitRunner(); return; }
  if (action === 'lesson-complete') {
    try {
      await api('/api/module/strategy/lesson/' + el.dataset.id + '/complete', { method: 'POST' });
      const fresh = await api('/api/progress');
      state.progress = fresh;
      toast('Lesson marked complete.', 'ok');
      viewModule(begin());
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (action === 'retry-assessment') { startAssessment(el.dataset.kind); return; }
  if (action === 'revise-practical') { state.practicalForm = true; viewPractical(begin()); return; }
  if (action === 'plan-toggle') {
    try {
      await api('/api/plan/' + el.dataset.id, { method: 'PATCH', body: JSON.stringify({ done: el.dataset.done !== '1' }) });
      viewProgress(begin());
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (action === 'plan-delete') {
    try { await api('/api/plan/' + el.dataset.id, { method: 'DELETE' }); viewProgress(begin()); }
    catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (action === 'coach-mode') {
    state.coach.mode = el.dataset.mode;
    state.coach.messages = [];
    renderCoach(begin());
    return;
  }
  if (action === 'coach-reset') { state.coach.messages = []; state.coach.busy = false; renderCoach(begin()); return; }
  if (action === 'coach-suggest') {
    const text = el.dataset.text;
    const input = $('#coach-input');
    if (input) { input.value = text; input.focus(); }
    return;
  }
  if (action === 'coach-begin-test') { sendCoach('Start with the first question'); return; }
  if (action === 'admin-tab') { state.admin.tab = el.dataset.tab; state.admin.editing = null; state.admin.showForm = false; location.hash = '#/admin/' + el.dataset.tab; if (location.hash === '#/admin/' + el.dataset.tab) router(); return; }
  if (action === 'admin-qfilter') { state.admin.qkind = el.dataset.kind; viewAdmin(begin(), 'questions'); return; }
  if (action === 'admin-qnew') { state.admin.editing = null; state.admin.showForm = true; viewAdmin(begin(), 'questions'); return; }
  if (action === 'admin-qcancel') { state.admin.editing = null; state.admin.showForm = false; viewAdmin(begin(), 'questions'); return; }
  if (action === 'admin-qedit') {
    const data = await api('/api/admin/questions');
    state.admin.editing = data.questions.find(q => q.id === el.dataset.id) || null;
    state.admin.showForm = true;
    viewAdmin(begin(), 'questions');
    return;
  }
  if (action === 'admin-qdelete') {
    if (!confirm('Delete this question? This cannot be undone.')) return;
    try { await api('/api/admin/questions/' + encodeURIComponent(el.dataset.id), { method: 'DELETE' }); toast('Question deleted.', 'ok'); viewAdmin(begin(), 'questions'); }
    catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (action === 'admin-module-select') {
    state.admin.moduleId = el.dataset.id; state.admin.lesson = null;
    state.admin.template = null; state.admin.newTemplate = false; state.admin.preview = false;
    viewAdmin(begin(), 'content'); return;
  }
  if (action === 'admin-module-new') {
    state.admin.newModule = !state.admin.newModule;
    viewAdmin(begin(), 'content'); return;
  }
  if (action === 'admin-module-status') {
    try {
      await api('/api/admin/modules/' + encodeURIComponent(state.admin.moduleId) + '/status', {
        method: 'POST', body: JSON.stringify({ status: el.dataset.status }),
      });
      toast(el.dataset.status === 'published' ? 'Module published.' : 'Module moved to draft.', 'ok');
      viewAdmin(begin(), 'content');
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (action === 'admin-preview') {
    state.admin.preview = !state.admin.preview;
    viewAdmin(begin(), 'content'); return;
  }
  if (action === 'admin-lesson-select') {
    state.admin.lesson = el.dataset.id;
    viewAdmin(begin(), 'content'); return;
  }
  if (action === 'admin-lesson-new') {
    try {
      const data = await api('/api/admin/modules/' + encodeURIComponent(state.admin.moduleId) + '/lessons', { method: 'POST' });
      state.admin.lesson = data.lesson.id;
      toast('Lesson added. Fill in the content and save.', 'ok');
      viewAdmin(begin(), 'content');
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (action === 'admin-lesson-delete') {
    if (!confirm('Delete this lesson? The revision history keeps a snapshot, but learners will lose it.')) return;
    try {
      await api('/api/admin/lessons/' + encodeURIComponent(el.dataset.id), { method: 'DELETE' });
      state.admin.lesson = null;
      toast('Lesson deleted.', 'ok');
      viewAdmin(begin(), 'content');
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (action === 'admin-template-select') {
    state.admin.template = el.dataset.slug; state.admin.newTemplate = false;
    viewAdmin(begin(), 'content'); return;
  }
  if (action === 'admin-template-new') {
    state.admin.template = null; state.admin.newTemplate = true;
    viewAdmin(begin(), 'content'); return;
  }
  if (action === 'admin-template-delete') {
    if (!confirm('Delete this template?')) return;
    try {
      await api('/api/admin/templates/' + encodeURIComponent(el.dataset.slug), { method: 'DELETE' });
      state.admin.template = null;
      toast('Template deleted.', 'ok');
      viewAdmin(begin(), 'content');
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (action === 'admin-review') {
    const card = el.closest('.review-card');
    const scores = {};
    $$('select[data-crit]', card).forEach(s => { scores[s.dataset.crit] = Number(s.value); });
    const note = $('textarea[data-note]', card).value;
    try {
      const res = await api('/api/admin/submissions/' + el.dataset.id + '/review', {
        method: 'POST', body: JSON.stringify({ scores, note }),
      });
      toast(res.passed ? 'Review saved — practical passed.' : 'Review saved — practical not passed.', res.passed ? 'ok' : '');
      viewAdmin(begin(), 'reviews');
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
});

function closeSidebar() {
  const side = $('#sidebar'); const back = $('#backdrop');
  if (side) side.classList.remove('open');
  if (back) back.classList.remove('show');
}

document.addEventListener('submit', async (e) => {
  const form = e.target.closest('form[data-form]');
  if (!form) return;
  e.preventDefault();
  const kind = form.dataset.form;
  if (kind === 'login') {
    doLogin(form.elements.email.value.trim(), form.elements.password.value);
    return;
  }
  if (kind === 'register') { doRegister(form); return; }
  if (kind === 'profile') {
    const body = {};
    ['business_name', 'sector', 'customer_type', 'stage', 'team_size', 'revenue_band', 'years', 'main_challenge'].forEach(k => { body[k] = form.elements[k].value.trim(); });
    try {
      const data = await api('/api/profile', { method: 'PUT', body: JSON.stringify(body) });
      state.progress = data.progress;
      state.editProfile = false;
      toast('Business profile saved.', 'ok');
      viewCheckup(begin());
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (kind === 'practical') {
    const responses = {};
    form.querySelectorAll('textarea').forEach(t => { responses[t.name] = t.value.trim(); });
    try {
      const data = await api('/api/practical/submit', { method: 'POST', body: JSON.stringify({ responses }) });
      state.practicalForm = false;
      state.progress = null;
      toast(data.message, 'ok');
      viewPractical(begin());
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (kind === 'plan-add') {
    const body = { title: form.elements.title.value.trim(), detail: '', due: form.elements.due.value || '' };
    try {
      await api('/api/plan', { method: 'POST', body: JSON.stringify(body) });
      toast('Action added to your plan.', 'ok');
      viewProgress(begin());
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (kind === 'coach-send') {
    const input = form.elements.message;
    const text = input.value;
    if (!text.trim()) return;
    input.value = '';
    sendCoach(text);
    return;
  }
  if (kind === 'question-save') {
    const el = form.elements;
    const options = el.options.value.split('\n').map(s => s.trim()).filter(Boolean);
    const body = {
      kind: el.kind.value, component: el.component.value, topic: el.topic.value.trim(),
      prompt: el.prompt.value.trim(), options, correct: Number(el.correct.value),
      explanation: el.explanation.value.trim(), active: el.active.checked,
    };
    const editing = state.admin.editing;
    try {
      await api('/api/admin/questions' + (editing ? '/' + encodeURIComponent(editing.id) : ''), {
        method: editing ? 'PUT' : 'POST', body: JSON.stringify(body),
      });
      state.admin.editing = null; state.admin.showForm = false;
      toast(editing ? 'Question updated.' : 'Question created.', 'ok');
      viewAdmin(begin(), 'questions');
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (kind === 'module-new') {
    const el = form.elements;
    try {
      const data = await api('/api/admin/modules', {
        method: 'POST',
        body: JSON.stringify({
          id: el.id.value.trim().toLowerCase(), component: el.component.value,
          title: el.title.value.trim(),
        }),
      });
      state.admin.moduleId = data.module.id;
      state.admin.newModule = false; state.admin.lesson = null;
      toast('Draft module created. Add lessons, questions and a practical before publishing.', 'ok');
      viewAdmin(begin(), 'content');
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (kind === 'practical-save') {
    const el = form.elements;
    const splitRows = (value) => value.split('\n').map(line => line.split('|').map(s => s.trim())).filter(row => row[0]);
    const criteria = splitRows(el.criteria.value).map(row => ({
      id: row[0].toLowerCase(), label: row[1] || row[0], hint: row[2] || '',
    }));
    const prompts = splitRows(el.prompts.value).map(row => ({
      id: row[0].toLowerCase(), criterion: row[1] || '', label: row[2] || row[0], placeholder: row[3] || '',
    }));
    try {
      await api('/api/admin/modules/' + encodeURIComponent(state.admin.moduleId), {
        method: 'PUT',
        body: JSON.stringify({
          practical: {
            title: el.practical_title.value.trim(),
            intro: el.practical_intro.value.trim(),
            criteria,
            prompts,
          },
        }),
      });
      toast('Practical assignment saved.', 'ok');
      viewAdmin(begin(), 'content');
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (kind === 'module-meta') {
    const el = form.elements;
    const paragraphs = (value) => value.split(/\n\s*\n/).map(s => s.trim()).filter(Boolean);
    try {
      await api('/api/admin/modules/' + encodeURIComponent(state.admin.moduleId), {
        method: 'PUT',
        body: JSON.stringify({
          title: el.title.value.trim(), tagline: el.tagline.value.trim(), level: el.level.value,
          hours: el.hours.value.trim(), outcome: el.outcome.value.trim(),
          intro: paragraphs(el.intro.value),
        }),
      });
      toast('Module details saved.', 'ok');
      viewAdmin(begin(), 'content');
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (kind === 'lesson-save') {
    const el = form.elements;
    const lines = (value) => value.split('\n').map(s => s.trim()).filter(Boolean);
    const paragraphs = (value) => value.split(/\n\s*\n/).map(s => s.trim()).filter(Boolean);
    const lessonId = el.lesson_id.value;
    try {
      await api('/api/admin/lessons/' + encodeURIComponent(lessonId), {
        method: 'PUT',
        body: JSON.stringify({
          title: el.title.value.trim(),
          minutes: Number(el.minutes.value),
          summary: el.summary.value.trim(),
          body: {
            explanation: paragraphs(el.explanation.value),
            example: { title: el.example_title.value.trim(), text: el.example_text.value.trim() },
            do: lines(el['do'].value),
            dont: lines(el['dont'].value),
            why: el.why.value.trim(),
            mistakes: lines(el.mistakes.value),
            exercise: { prompt: el.exercise_prompt.value.trim(), steps: lines(el.exercise_steps.value) },
          },
        }),
      });
      toast('Lesson saved. Learners see this immediately when the module is published.', 'ok');
      viewAdmin(begin(), 'content');
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (kind === 'template-save') {
    const el = form.elements;
    try {
      await api('/api/admin/modules/' + encodeURIComponent(state.admin.moduleId) + '/templates', {
        method: 'PUT',
        body: JSON.stringify({
          slug: el.slug.value.trim().toLowerCase(),
          title: el.title.value.trim(),
          description: el.description.value.trim(),
          filename: el.filename.value.trim(),
          body: el.body.value,
        }),
      });
      state.admin.template = el.slug.value.trim().toLowerCase();
      state.admin.newTemplate = false;
      toast('Template saved.', 'ok');
      viewAdmin(begin(), 'content');
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (kind === 'admin-settings') {
    const body = {
      quiz_pass: Number(form.elements.quiz_pass.value), scenario_pass: Number(form.elements.scenario_pass.value),
      rubric_min: Number(form.elements.rubric_min.value), rubric_floor: Number(form.elements.rubric_floor.value),
    };
    try {
      const data = await api('/api/admin/settings', { method: 'PUT', body: JSON.stringify(body) });
      state.settings = data.settings;
      toast('Passing standards updated.', 'ok');
      viewAdmin(begin(), 'settings');
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
  if (kind === 'admin-content') {
    const el = form.elements;
    const lessonId = el.lesson_id.value;
    const fields = {
      title: el.title.value.trim(),
      summary: el.summary.value.trim(),
      explanation: el.explanation.value.trim(),
    };
    try {
      for (const [field, value] of Object.entries(fields)) {
        await api('/api/admin/content', { method: 'PUT', body: JSON.stringify({ lesson_id: lessonId, field, value }) });
      }
      toast('Lesson content saved.', 'ok');
      viewAdmin(begin(), 'settings');
    } catch (err) { toast(err.message, 'err'); }
    return;
  }
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey && e.target && e.target.id === 'coach-input') {
    e.preventDefault();
    const form = e.target.closest('form');
    if (form) form.requestSubmit();
  }
  if (e.key === 'Escape') closeSidebar();
});

window.addEventListener('hashchange', () => { router(); });

/* expose a tiny debug handle for development */
window.__bizready = { state, router };

/* ------------------------------------------------------------------ boot */
(async function boot() {
  try {
    const data = await api('/api/bootstrap');
    state.components = data.components || [];
    state.settings = data.settings || {};
    state.ai = data.ai || { configured: false, mode: 'demo' };
    state.user = data.user;
    state.progress = data.progress || null;
    if (state.user) router(); else renderAuth();
  } catch (err) {
    $('#app').innerHTML = `<div style="min-height:100vh;display:grid;place-items:center;padding:24px">
      <div class="card card-pad" style="max-width:420px;text-align:center">
        <div class="brand-mark" style="margin:0 auto 14px">f</div>
        <h2>futurePreneur could not start</h2>
        <p class="small muted">${esc(err.message)}</p>
        <p class="tiny muted">Make sure the server is running: <code>python run.py</code></p>
        <button class="btn btn-primary btn-sm" type="button" id="boot-reload">Reload</button>
      </div></div>`;
    const reload = document.getElementById('boot-reload');
    if (reload) reload.addEventListener('click', () => location.reload());
  }
})();
