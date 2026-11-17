// TinyBrowser + raw CDP: inspect public registration controls, never fill or submit.
const url = process.argv[2] || '';
const key = process.env.TINYFISH_API_KEY;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let session, socket;
const inspectionDeadline = Date.now() + 105000;
const remainingInspectionMs = () => Math.max(0, inspectionDeadline - Date.now());
let result = {
  status: 'unknown', url, method: 'tinybrowser', verified: false, created: false, creation_status: 'not_started',
  checked_at: new Date().toISOString(), cleanup_confirmed: null, cleanup_error: null,
  fields: [], buttons: [], button_observations: [], form_observations: [], form_observation: null,
  note: 'Registration controls have not been established. No fields filled and no form submitted.'
};

// This function is serialized into Runtime.evaluate. It only reads the DOM.
function inspectRegistration() {
  const textOf = el => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const visible = el => {
    if (!el?.getClientRects().length) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return false;
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (style.display === 'none' || ['hidden', 'collapse'].includes(style.visibility) || Number(style.opacity) === 0 || node.hidden) return false;
    }
    return true;
  };
  const stateOf = el => {
    const disabled = Boolean(el.disabled || el.matches(':disabled'));
    const readOnly = Boolean(el.readOnly || (el.getAttribute('aria-readonly') || '').toLowerCase() === 'true');
    const ariaDisabled = Boolean(el.closest('[aria-disabled="true" i]'));
    const inert = Boolean(el.closest('[inert]'));
    const displayed = visible(el);
    return { visible: displayed, disabled, readOnly, aria_disabled: ariaDisabled, inert,
      enabled: displayed && !disabled && !readOnly && !ariaDisabled && !inert };
  };
  const fieldOf = el => {
    const labels = [...(el.labels || [])].map(textOf).join(' ');
    const type = (el.type || '').toLowerCase();
    const descriptor = [el.name, el.id, el.placeholder, el.autocomplete, el.getAttribute('aria-label'), labels].join(' ');
    const relevant = ['email', 'password', 'tel'].includes(type) ||
      (type === 'text' && /\bemail\b|e-mail|username|user_name|phone|mobile/i.test(descriptor));
    return { type, name: el.name || '', id: el.id || '', placeholder: el.placeholder || '',
      label: labels, aria_label: el.getAttribute('aria-label') || '', autocomplete: el.autocomplete || '',
      required: Boolean(el.required), relevant, ...stateOf(el) };
  };
  const buttonSelector = 'button,input[type="submit"],input[type="button"],[role="button"],a[href]';
  const buttonOf = el => {
    const label = (el.innerText || (el.tagName === 'INPUT' ? el.value : '') || el.getAttribute('aria-label') || el.getAttribute('title') || '').replace(/\s+/g, ' ').trim();
    const registration = /\b(?:create|open|start)\b.{0,35}\b(?:account|workspace)\b|\bsign[ -]?up\b|\bregister\b/i.test(label);
    const sso = /\b(?:continue|sign[ -]?up|register) with (?:google|github|microsoft|apple|sso|saml)\b/i.test(label) || /^(?:google|github|microsoft|apple|sso|saml)$/i.test(label);
    const continuation = /^(?:continue|next|get started|start free trial)$/i.test(label);
    return { text: label, tag: el.tagName.toLowerCase(), type: el.type || '', role: el.getAttribute('role') || '',
      action_kind: sso ? 'sso' : registration ? 'registration' : continuation ? 'continue' : 'other',
      ...stateOf(el) };
  };
  const fields = [...document.querySelectorAll('input')].filter(visible);
  const scopes = new Set();
  for (const field of fields) {
    const form = field.closest('form');
    if (form) { scopes.add(form); continue; }
    // SPA registration can use a local div instead of a form. Never widen to body.
    let ancestor = field.parentElement;
    for (let depth = 0; ancestor && depth < 8 && !['BODY', 'HTML'].includes(ancestor.tagName); depth++, ancestor = ancestor.parentElement) {
      const scopeText = textOf(ancestor);
      if (scopeText.length > 6000) break;
      if (scopeText.length && ancestor.querySelector(buttonSelector) &&
          /create.{0,35}(?:account|workspace)|sign[ -]?up|register/i.test(scopeText)) {
        scopes.add(ancestor); break;
      }
    }
  }
  const observations = [...scopes].slice(0, 20).map((scope, index) => {
    const context = textOf(scope).slice(0, 6000);
    const scopeFields = [...scope.querySelectorAll('input')].filter(visible).map(fieldOf);
    const scopeButtons = [...scope.querySelectorAll(buttonSelector)].filter(visible).map(buttonOf).filter(b => b.text).slice(0, 30);
    const enabledFields = scopeFields.filter(f => f.relevant && f.enabled);
    const enabledActions = scopeButtons.filter(b => b.enabled && ['registration', 'sso', 'continue'].includes(b.action_kind));
    const strongAccount = /\b(?:create|open|start)\b.{0,35}\b(?:account|workspace)\b|\bregister(?:ing)?\b.{0,25}\baccount\b/i.test(context);
    const genericRegistration = /\bsign[ -]?up\b|\bregister\b/i.test(context);
    const newsletterLanguage = /\bnewsletter\b|\bmailing list\b|subscribe.{0,35}(?:updates|news|emails)/i.test(context);
    const newsletter = newsletterLanguage && !strongAccount;
    const accountRegistration = strongAccount || (genericRegistration && !newsletter);
    const local = context.length < 6000 && scopeFields.length <= 12 && visible(scope);
    const qualifies = local && accountRegistration && !newsletter && enabledFields.length > 0 && enabledActions.length > 0;
    const action = scope.getAttribute('action');
    let actionPath = null;
    if (action) { try { const destination = new URL(action, location.href); actionPath = destination.origin + destination.pathname; } catch {} }
    return { index, scope: scope.tagName.toLowerCase(), id: scope.id || '', role: scope.getAttribute('role') || '',
      action_path: actionPath, method: scope.getAttribute('method') || '', visible: visible(scope), local,
      account_registration: accountRegistration, newsletter, newsletter_language: newsletterLanguage,
      enabled_relevant_fields: enabledFields.length, enabled_registration_actions: enabledActions.length,
      qualifies, fields: scopeFields, buttons: scopeButtons, text: context,
      reason: qualifies ? 'Enabled relevant input and enabled registration action share a visible local account-registration scope.' :
        newsletter ? 'The local scope is newsletter or mailing-list registration.' :
        !accountRegistration ? 'The local scope does not establish account registration.' :
        !local ? 'The scope is hidden or too broad to establish one registration form.' :
        !enabledFields.length ? 'No enabled editable email, password, phone, or username input in this scope.' :
        'No enabled registration/continue/SSO action in the same scope.' };
  });
  const chosen = observations.find(f => f.qualifies) || observations.find(f => f.account_registration && !f.newsletter) || observations[0] || null;
  return { final_url: location.href, title: document.title,
    fields: chosen?.fields || fields.map(fieldOf).slice(0, 30),
    buttons: (chosen?.buttons || []).map(b => b.text),
    button_observations: chosen?.buttons || [], form_observation: chosen,
    form_observations: observations,
    text: chosen?.text || '', verified: Boolean(chosen?.qualifies),
    note: chosen?.qualifies ?
      'Enabled registration input and action observed in the same visible account-registration form or local section. No fields filled and no form submitted.' :
      (chosen?.reason || 'No visible local account-registration form with both an enabled relevant input and registration action was found.') + ' No fields filled and no form submitted.' };
}

try {
  const parsed = new URL(url);
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) throw new Error('A public signup URL is required');
  if (!key) throw new Error('TINYFISH_API_KEY is not configured');
  result.creation_status = 'pending';
  const response = await fetch('https://api.browser.tinyfish.ai', {
    method: 'POST', headers: { 'X-API-Key': key, 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, timeout_seconds: 90 }), signal: AbortSignal.timeout(60000)
  });
  if (!response.ok) {
    result.creation_status = response.status >= 500 ? 'uncertain' : 'rejected';
    throw new Error(`TinyBrowser HTTP ${response.status}`);
  }
  session = await response.json();
  result.created = true;
  result.creation_status = 'created';
  result.session_id = session.session_id;
  if (!session.cdp_url || !session.session_id) throw new Error('TinyBrowser response omitted connection or cleanup identity');
  const pending = new Map();
  let counter = 0;
  socket = new WebSocket(session.cdp_url);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('CDP connect timeout')), Math.min(20000, remainingInspectionMs()));
    socket.addEventListener('open', () => { clearTimeout(timer); resolve(); }, { once: true });
    socket.addEventListener('error', () => { clearTimeout(timer); reject(new Error('CDP connection failed')); }, { once: true });
  });
  socket.addEventListener('message', event => {
    let message;
    try { message = JSON.parse(String(event.data)); } catch { return; }
    const call = pending.get(message.id);
    if (call) { pending.delete(message.id); clearTimeout(call.timer); message.error ? call.reject(new Error(message.error.message)) : call.resolve(message.result); }
  });
  const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    if (!remainingInspectionMs()) { reject(new Error('Registration inspection time budget reached')); return; }
    const id = ++counter;
    const timer = setTimeout(() => { if (pending.has(id)) { pending.delete(id); reject(new Error('CDP command timeout')); } }, Math.min(20000, remainingInspectionMs()));
    pending.set(id, { resolve, reject, timer });
    try { socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) })); }
    catch (error) { clearTimeout(timer); pending.delete(id); reject(error); }
  });
  let target;
  for (let i = 0; i < 12; i++) {
    const targets = await send('Target.getTargets');
    target = targets.targetInfos.find(t => t.type === 'page' && !['about:blank', ''].includes(t.url));
    if (target) break;
    await sleep(1000);
  }
  if (!target) throw new Error('Browser did not finish startup navigation');
  const attached = await send('Target.attachToTarget', { targetId: target.targetId, flatten: true });
  const expression = `(${inspectRegistration.toString()})()`;
  let observation;
  for (let i = 0; i < 15; i++) {
    const response = await send('Runtime.evaluate', { expression, returnByValue: true }, attached.sessionId);
    if (response.exceptionDetails) throw new Error('Registration DOM inspection failed');
    observation = response.result?.value;
    if (observation?.verified) break;
    await sleep(1000);
  }
  if (!observation) throw new Error('Browser did not return a registration observation');
  result = { ...result, ...observation, status: observation.verified ? 'active' : 'unknown', checked_at: new Date().toISOString() };
} catch (error) {
  if (result.creation_status === 'pending') result.creation_status = 'uncertain';
  result.error = String(error.message);
  result.verified = false;
  result.status = 'unknown';
  process.exitCode = 1;
} finally {
  try { socket?.close(); } catch {}
  if (session?.session_id) {
    try {
      const closed = await fetch(`https://api.browser.tinyfish.ai/${session.session_id}`, {
        method: 'DELETE', headers: { 'X-API-Key': key }, signal: AbortSignal.timeout(15000)
      });
      result.cleanup_confirmed = closed.ok;
      if (!closed.ok) result.cleanup_error = `TinyBrowser cleanup HTTP ${closed.status}; 90-second inactivity expiry is the fallback.`;
    } catch (error) {
      result.cleanup_confirmed = false;
      result.cleanup_error = `TinyBrowser cleanup failed: ${error.message}. 90-second inactivity expiry is the fallback.`;
    }
  } else if (result.created) {
    result.cleanup_confirmed = false;
    result.cleanup_error = 'Session creation returned no cleanup identity; 90-second inactivity expiry is the fallback.';
  } else if (result.creation_status === 'uncertain') {
    result.cleanup_confirmed = false;
    result.cleanup_error = 'Session creation outcome is uncertain and no cleanup identity was returned; 90-second inactivity expiry is the fallback. No replacement session was started.';
  }
  // Exactly one result is emitted, after cleanup, so callers retain its outcome.
  console.log(JSON.stringify(result));
}

