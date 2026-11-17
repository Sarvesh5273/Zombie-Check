"use strict";

const $ = (id) => document.getElementById(id);
const signalKinds = ["blog", "release", "jobs", "social", "signup"];
const companySignalLabels = { blog: "Blog & news", release: "Product releases", jobs: "Open roles", social: "Social & developer activity", signup: "Sign-up & onboarding" };
const jobSignalLabels = { blog: "Employer news", release: "Employer releases", jobs: "Exact job listing", social: "Employer activity", signup: "Application intake" };
const signalSymbols = { blog: "▧", release: "⤴", jobs: "▢", social: "◉", signup: "↪" };
const statusLabels = { ready: "Ready to check", running: "Checking the live web", pausing: "Saving your progress", paused: "Audit paused", complete: "Every row has a verified verdict", needs_review: "Checks saved. Evidence needs review.", error: "Audit stopped with an error" };
const state = {
  config: null, audits: [], audit: null, rows: [], csv: "", preview: null, fileName: "",
  filter: "all", search: "", page: 0, pageSize: 25, selectedRowId: null, report: null,
  generation: 0, refreshing: false, toastTimer: null, drawerOrigin: null,
};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (s) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[s]));
}

function linkUrl(value) {
  try {
    const url = new URL(String(value));
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : "";
  } catch { return ""; }
}

function domain(value) {
  try { return new URL(value).hostname.replace(/^www\./, ""); }
  catch { return String(value || "No website supplied"); }
}

function isJobMode(audit = state.audit) { return audit?.config?.mode === "jobs"; }
function activeSignalLabels() { return isJobMode() ? jobSignalLabels : companySignalLabels; }
function headerIndex(headers, names) {
  return headers.findIndex(header => names.includes(String(header).trim().toLowerCase().replace(/[_-]+/g, " ")));
}
function mappedJobColumn(audit, key) {
  const column = audit?.config?.job_columns?.[key];
  return Number.isInteger(column) ? column : typeof column === "string" ? (audit?.headers || []).indexOf(column) : -1;
}
function rowDisplayName(row, audit = state.audit) {
  if (!isJobMode(audit)) return row.name || "Unnamed company";
  const mapped = mappedJobColumn(audit, "title");
  const index = mapped >= 0 ? mapped : Number.isInteger(audit?.config?.name_column) ? audit.config.name_column : headerIndex(audit?.headers || [], ["title", "job title", "role", "position", "position title"]);
  return (index >= 0 ? row.original?.[index] : null) || row.name || "Untitled job post";
}
function rowDisplayUrl(row, audit = state.audit) {
  if (!isJobMode(audit)) return row.website || "";
  const mapped = mappedJobColumn(audit, "job_url");
  const index = mapped >= 0 ? mapped : Number.isInteger(audit?.config?.url_column) ? audit.config.url_column : headerIndex(audit?.headers || [], ["job url", "posting url", "listing url", "job link", "posting link"]);
  return (index >= 0 ? row.original?.[index] : null) || row.website || "";
}
function rowEmployer(row, audit = state.audit) {
  const mapped = mappedJobColumn(audit, "employer");
  const index = mapped >= 0 ? mapped : headerIndex(audit?.headers || [], ["employer", "company", "company name", "organization", "organisation"]);
  return index >= 0 ? String(row.original?.[index] || "") : "";
}
function observationLimitNote() {
  return isJobMode()
    ? "Alive verifies the current listing and application intake. It does not establish a funded vacancy or completed hiring. No application was submitted."
    : "Sign-up observations establish a reachable entry or form. No account was created and no registration submission was tested.";
}
function effectiveImportMode() {
  const selection = $("auditMode").value;
  if (selection !== "auto") return selection;
  return state.preview?.detected_mode === "jobs" ? "jobs" : "companies";
}
function mappingProblems() {
  const problems = {};
  const count = state.preview?.headers?.length || 0;
  const nameRaw = $("nameColumn").value;
  const name = Number(nameRaw);
  const url = $("urlColumn").value;
  if (!count || nameRaw === "" || !Number.isInteger(name) || name < 0 || name >= count) {
    problems.nameColumn = "Choose the column that names this company or exact job post.";
  }
  if (effectiveImportMode() === "jobs" && url === "") {
    problems.urlColumn = "Choose the exact job-listing URL column. Employer websites alone cannot verify a specific posting.";
  } else if (url !== "" && (!Number.isInteger(Number(url)) || Number(url) < 0 || Number(url) >= count)) {
    problems.urlColumn = "Choose a valid URL column from this spreadsheet.";
  }
  if (effectiveImportMode() === "jobs") {
    for (const [field, label] of [["employerColumn", "employer name"], ["employerWebsiteColumn", "employer website"]]) {
      const selection = $(field).value;
      if (selection === "" || !Number.isInteger(Number(selection)) || Number(selection) < 0 || Number(selection) >= count) {
        problems[field] = "Choose the " + label + " column so the exact posting can be linked to its employer.";
      }
    }
  }
  const budget = $("importBudget");
  if (budget.value === "" || !Number.isFinite(Number(budget.value)) || Number(budget.value) < 0 || Number(budget.value) > 100) {
    problems.importBudget = "Enter a research cap from $0 to $100.";
  }
  return problems;
}
function displayFieldErrors(problems) {
  for (const field of ["nameColumn", "urlColumn", "employerColumn", "employerWebsiteColumn", "importBudget"]) {
    const element = $(field + "Error");
    const message = problems[field];
    element.textContent = message || "";
    element.hidden = !message;
    $(field).setAttribute("aria-invalid", message ? "true" : "false");
  }
}
function showImportError(message, problems = {}) {
  displayFieldErrors(problems);
  const summary = $("importErrorSummary");
  const links = Object.entries(problems).map(([field, text]) =>
    '<li><a href="#' + esc(field) + '">' + esc(text) + '</a></li>').join("");
  summary.innerHTML = "<strong>Check this before starting the audit.</strong><p>" + esc(message) +
    "</p>" + (links ? "<ul>" + links + "</ul>" : "");
  summary.hidden = false;
  summary.focus();
}
function updateMappingPreview(clearError = false) {
  const preview = state.preview;
  if (!preview) return;
  const sample = index => {
    if (index === "" || !Number.isInteger(Number(index))) return "";
    return [...new Set(preview.rows.map(row => String(row[Number(index)] || "").trim()).filter(Boolean))].slice(0,2).join(" · ");
  };
  const nameSample = sample($("nameColumn").value);
  const urlSample = sample($("urlColumn").value);
  $("nameColumnHelp").textContent = nameSample ? "Preview: " + nameSample :
    (effectiveImportMode() === "jobs" ? "Map the original job title or posting identifier." : "Map the original company, tool, or vendor name.");
  $("urlColumnHelp").textContent = urlSample ? "Preview: " + urlSample :
    (effectiveImportMode() === "jobs" ? "Use the listing URL for this exact job, not just its employer's homepage." : "A blank mapping lets TinySearch discover the official website.");
  for (const [field, fallback] of [["employerColumn", "Choose the employer's name."], ["employerWebsiteColumn", "Choose the employer's official website."]]) {
    const example = sample($(field).value);
    $(field + "Help").textContent = example ? "Preview: " + example : fallback;
  }
  displayFieldErrors(mappingProblems());
  if (clearError) $("importErrorSummary").hidden = true;
}
function updateImportMode(remap = false) {
  const jobs = effectiveImportMode() === "jobs";
  const detected = state.preview?.detected_mode;
  $("jobColumnsFieldset").hidden = !jobs;
  $("nameMappingLabel").textContent = jobs ? "Job title column" : "Company name column";
  $("urlMappingLabel").textContent = jobs ? "Exact job URL column" : "Website column";
  const emptyUrl = $("urlColumn").querySelector('option[value=""]');
  if (emptyUrl) emptyUrl.textContent = jobs ? "Select the exact listing URL column" : "Discover from company name";
  $("fullStrategyDescription").textContent = jobs
    ? "Research every listed job through TinySet, then verify its sources with live Fetch."
    : "Research every company through TinySet, then verify its sources with live Fetch.";
  $("importModeHint").textContent = jobs
    ? "Checks the exact job listing, application intake, and employer activity. A live intake does not prove a funded vacancy or completed hiring."
    : (detected ? "Auto detected companies/vendors. Choose Job posts for a listing-level audit." : "The server detects the list type from your column headings. You can override it.");
  if (remap && state.preview) {
    const headers = state.preview.headers || [];
    const nameIndex = headerIndex(headers, jobs ? ["title", "job title", "role", "position", "position title"] : ["company", "company name", "employer", "name", "tool", "vendor", "organization"]);
    const urlIndex = headerIndex(headers, jobs ? ["job url", "posting url", "listing url", "job link", "posting link", "url"] : ["website", "website url", "domain", "homepage", "url", "company url"]);
    if (nameIndex >= 0) $("nameColumn").value = nameIndex;
    if (urlIndex >= 0) $("urlColumn").value = urlIndex;
  }
  updateMappingPreview(true);
  updateBudgetExplanation();
}
function populateJobColumns(preview) {
  const options = preview.headers.map((heading, index) =>
    '<option value="' + index + '">' + esc(heading || "Column " + (index + 1)) + '</option>').join("");
  const aliases = {
    employer: ["employer", "company", "company name", "organization", "organisation"],
    employer_website: ["employer website", "company website", "company domain", "employer domain"],
    board_token: ["board token", "greenhouse token", "greenhouse board"],
    job_id: ["job id", "posting id", "requisition id"],
    job_api_url: ["job api url", "posting api url", "api url"]
  };
  for (const [key, field] of Object.entries({employer:"employerColumn",employer_website:"employerWebsiteColumn",board_token:"boardTokenColumn",job_id:"jobIdColumn",job_api_url:"jobApiColumn"})) {
    $(field).innerHTML = '<option value="">' + (key === "employer" || key === "employer_website" ? "Choose column" : "Auto / not supplied") + '</option>' + options;
    const hint = preview.job_columns?.[key];
    const suggested = Number.isInteger(hint) ? hint : typeof hint === "string" ? preview.headers.indexOf(hint) : headerIndex(preview.headers, aliases[key]);
    $(field).value = suggested >= 0 ? suggested : "";
  }
}
function selectedJobColumns() {
  if (effectiveImportMode() !== "jobs") return undefined;
  const optional = field => $(field).value === "" ? null : Number($(field).value);
  return { title:Number($("nameColumn").value),job_url:Number($("urlColumn").value),
    employer:optional("employerColumn"),employer_website:optional("employerWebsiteColumn"),
    board_token:optional("boardTokenColumn"),job_id:optional("jobIdColumn"),job_api_url:optional("jobApiColumn") };
}

function formatNumber(value) { return Number(value || 0).toLocaleString(); }
function money(value) { return `$${Number(value || 0).toFixed(2)}`; }
function dateLabel(value, includeTime = false) {
  if (!value) return "Not established";
  const date = new Date(value.length === 10 ? `${value}T12:00:00` : value);
  if (Number.isNaN(date.valueOf())) return String(value);
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric", ...(includeTime ? { hour: "2-digit", minute: "2-digit" } : {}) });
}

function toast(message, error = false) {
  clearTimeout(state.toastTimer);
  $("toast").textContent = message;
  $("toast").classList.toggle("error", error);
  $("toast").hidden = false;
  state.toastTimer = setTimeout(() => { $("toast").hidden = true; }, error ? 8500 : 4500);
}

function loading(show, text = "Reading your list…") {
  $("loadingIndicator").hidden = !show;
  $("loadingText").textContent = text;
}

async function api(path, options = {}) {
  const token = sessionStorage.getItem("zc-access-token") || "";
  const headers = { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(token ? { "X-Audit-Token": token } : {}), ...(options.headers || {}) };
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { message = (await response.json()).error || message; } catch {}
    if (response.status === 401 && !$("settingsDialog").open) $("settingsDialog").showModal();
    throw new Error(message);
  }
  return options.blob ? response.blob() : response.json();
}

function post(path, body = {}) { return api(path, { method: "POST", body: JSON.stringify(body) }); }

function showWelcome() {
  state.generation += 1;
  state.audit = null;
  state.selectedRowId = null;
  closeDrawer();
  $("welcomeView").hidden = false;
  $("auditView").hidden = true;
  renderAuditList();
  $("dropZone").focus({ preventScroll: true });
}

function renderAuditList() {
  $("auditCount").textContent = state.audits.length;
  if (!state.audits.length) {
    $("auditList").innerHTML = '<p class="sidebar-empty">Your checked lists live here.</p>';
    return;
  }
  $("auditList").innerHTML = state.audits.map((audit) => `<button class="audit-nav${state.audit?.id === audit.id ? " selected" : ""}" data-audit="${esc(audit.id)}" title="${esc(audit.name)}"><span aria-hidden="true">▤</span><span class="audit-nav-name">${esc(audit.name)}</span><span class="audit-nav-dot" aria-hidden="true"></span></button>`).join("");
  $("auditList").querySelectorAll("[data-audit]").forEach((button) => button.addEventListener("click", () => selectAudit(button.dataset.audit)));
}

async function loadAudits() {
  const data = await api("/api/audits");
  state.audits = data.audits || [];
  renderAuditList();
}

async function connect() {
  try {
    state.config = await api("/api/config");
    const configured = state.config.key_configured;
    $("connectionBadge").className = `connection-badge ${configured ? "connected" : "error"}`;
    $("connectionBadge").innerHTML = `<i></i>${configured ? "TinyFish connected" : "TinyFish key missing"}`;
    $("serverVersion").textContent = `Server v${state.config.version || "0.1.0"}`;
    $("importBudget").value = state.config.budget_default ?? 5;
    await loadAudits();
  } catch (error) {
    $("connectionBadge").className = "connection-badge error";
    $("connectionBadge").innerHTML = "<i></i>Connection needs attention";
    toast(error.message, true);
  }
}

async function importContent(csv, fileName) {
  if (!csv.trim()) { toast("The CSV is empty.", true); return; }
  loading(true, "Checking columns and original rows…");
  try {
    const preview = await post("/api/preview", { csv });
    state.csv = csv;
    state.preview = preview;
    $("importErrorSummary").hidden = true;
    state.fileName = fileName || "pasted-list.csv";
    $("importFileName").textContent = state.fileName;
    $("importFileMeta").textContent = `${formatNumber(preview.row_count)} rows · ${preview.headers.length} original columns`;
    $("importName").value = state.fileName.replace(/\.(csv|tsv)$/i, "").replace(/[_-]+/g, " ") || "Company list audit";
    $("nameColumn").innerHTML = preview.headers.map((heading, index) => `<option value="${index}">${esc(heading || `Column ${index + 1}`)}</option>`).join("");
    $("urlColumn").innerHTML = '<option value="">Discover from company name</option>' + preview.headers.map((heading, index) => `<option value="${index}">${esc(heading || `Column ${index + 1}`)}</option>`).join("");
    $("nameColumn").value = preview.name_column;
    $("urlColumn").value = preview.url_column === null ? "" : preview.url_column;
    populateJobColumns(preview);
    $("auditMode").value = "auto";
    updateImportMode(true);
    $("previewRowsNote").textContent = `First ${preview.rows.length} of ${formatNumber(preview.row_count)}`;
    $("inputPreview").innerHTML = `<thead><tr>${preview.headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${preview.rows.map((row) => `<tr>${row.map((cell) => `<td title="${esc(cell)}">${esc(cell)}</td>`).join("")}</tr>`).join("")}</tbody>`;
    $("importForm").querySelector('[name="strategy"][value="triage"]').checked = true;
    $("importBudget").value = state.config?.budget_default ?? 5;
    updateImportMode();
    $("importDialog").showModal();
  } catch (error) { toast(error.message, true); }
  finally { loading(false); }
}

async function readFile(file) {
  if (!file) return;
  if (file.size > 20 * 1024 * 1024) { toast("This file exceeds 20 MB. Split the list or choose a smaller CSV.", true); return; }
  if (!/\.(csv|tsv)$/i.test(file.name)) { toast("Choose a CSV or TSV spreadsheet export.", true); return; }
  try { await importContent(await file.text(), file.name); }
  catch (error) { toast(`Couldn’t read this file: ${error.message}`, true); }
  finally { $("fileInput").value = ""; }
}

function updateBudgetExplanation() {
  const rows = state.preview?.row_count || 0;
  const strategy = $("importForm").querySelector('[name="strategy"]:checked').value;
  const cap = Number($("importBudget").value || 0);
  $("importFooterBudget").textContent = money(cap) + " paid usage cap · Original rows retained";
  const estimate = rows * 0.10;
  const full = strategy === "full";
  const jobs = effectiveImportMode() === "jobs";
  $("budgetExplanation").textContent = jobs
    ? "TinySet researches shared employer context. Exact listings and application intake are checked for every job row. The cap covers paid employer research and verification."
    : full
      ? "Up to " + money(estimate) + " at $0.10 per unique researched company before source verification. The server validates the actual unique-company cost against your cap."
      : "The cap covers paid research and verification. The broad Search/Fetch pass checks all rows first. Unresolved rows remain visible when the cap is reached.";
  const notes = [];
  if (rows < 500) notes.push("This " + rows + "-row list is suitable for a pilot. The bounty’s scale requirement needs a real list of at least 500 rows.");
  if (!jobs && full && cap < estimate) notes.push("Your cap is below the upper estimate. The server checks unique companies before accepting a full-coverage audit.");
  if (!state.config?.key_configured) notes.push("The server needs a configured TinyFish API key before live research can start.");
  $("importWarning").hidden = !notes.length;
  $("importWarning").textContent = notes.join(" ");
  const problems = mappingProblems();
  displayFieldErrors(problems);
  $("createAudit").disabled = Object.keys(problems).length > 0;
}

async function createAudit(event) {
  event.preventDefault();
  if (!state.preview || !state.csv) return;
  const problems = mappingProblems();
  if (Object.keys(problems).length) {
    showImportError("The highlighted mappings or cap need a correction. Your CSV is retained.", problems);
    return;
  }
  $("importErrorSummary").hidden = true;
  const button = $("createAudit");
  button.disabled = true;
  loading(true, "Saving your original spreadsheet…");
  try {
    const audit = await post("/api/audits", {
      csv: state.csv, name: $("importName").value.trim() || "Company list audit",
      mode: $("auditMode").value,
      job_columns: selectedJobColumns(),
      name_column: Number($("nameColumn").value), url_column: $("urlColumn").value === "" ? null : Number($("urlColumn").value),
      budget: Number($("importBudget").value), strategy: $("importForm").querySelector('[name="strategy"]:checked').value,
    });
    $("importDialog").close();
    state.csv = "";
    state.preview = null;
    await loadAudits();
    await selectAudit(audit.id);
    if (state.config?.key_configured) await runAudit();
    else toast("Your original list is saved. Configure the TinyFish key on the server, then start the audit.", true);
  } catch (error) {
    showImportError(error.message);
    toast(error.message, true);
  }
  finally { updateBudgetExplanation(); loading(false); }
}

async function loadAllRows(id, generation) {
  const first = await api(`/api/audits/${id}/rows?limit=500&offset=0`);
  let rows = first.rows || [];
  const total = first.total || rows.length;
  for (let offset = 500; offset < total; offset += 500) {
    if (generation !== state.generation) return null;
    const page = await api(`/api/audits/${id}/rows?limit=500&offset=${offset}`);
    rows.push(...(page.rows || []));
  }
  return rows;
}

async function selectAudit(id) {
  const generation = ++state.generation;
  closeDrawer();
  loading(true, "Opening the evidence ledger…");
  try {
    const [audit, rows] = await Promise.all([api(`/api/audits/${id}`), loadAllRows(id, generation)]);
    if (generation !== state.generation || rows === null) return;
    state.audit = audit;
    state.rows = rows;
    state.page = 0;
    state.filter = "all";
    state.search = "";
    state.report = null;
    $("rowSearch").value = "";
    $("welcomeView").hidden = true;
    $("auditView").hidden = false;
    setFilter("all");
    renderAudit();
    renderAuditList();
    await loadEvents();
  } catch (error) { toast(error.message, true); }
  finally { if (generation === state.generation) loading(false); }
}

function renderAudit() {
  const audit = state.audit;
  if (!audit) return;
  const counts = audit.counts || {};
  const jobsMode = isJobMode(audit);
  $("jobModeNote").hidden = !jobsMode;
  $("totalSignalDetail").textContent = jobsMode ? "Five live signals per job post" : "Five live signals per company";
  $("aliveDetail").textContent = jobsMode ? "Current listing and intake verified" : "Verified signs of operation";
  $("slowingDetail").textContent = jobsMode ? "Older or uncertain listing evidence" : "Limited or older activity";
  $("zombieDetail").textContent = jobsMode ? "Closed or removed listing" : "Closure or parking evidence";
  $("rowSearch").placeholder = jobsMode ? "Find a job, employer, or listing" : "Find a company or domain";
  $("rowSearch").setAttribute("aria-label", $("rowSearch").placeholder);
  const checked = state.rows.filter((row) => row.result && Number(row.result.signals_checked || 0) >= 4).length;
  const finished = counts.done || 0;
  const review = counts.review || 0;
  const percent = audit.total ? Math.round(checked / audit.total * 100) : 0;
  $("auditName").textContent = audit.name;
  $("auditRowsMeta").textContent = `${formatNumber(audit.total)} original rows`;
  $("auditCreated").textContent = dateLabel(audit.created_at);
  $("auditStrategy").textContent = (jobsMode ? "Job posts · " : "") + (audit.config?.strategy === "full" ? "Full TinySet coverage" : "Budget triage");
  $("checkedCount").textContent = formatNumber(checked);
  $("totalCount").textContent = `/ ${formatNumber(audit.total)}`;
  $("aliveCount").textContent = formatNumber(audit.verdicts?.alive);
  $("slowingCount").textContent = formatNumber(audit.verdicts?.["slowing down"]);
  $("zombieCount").textContent = formatNumber(audit.verdicts?.zombie);
  $("progressTitle").textContent = statusLabels[audit.status] || audit.status;
  const descriptions = {
    ready: "Your input is saved. Start to check five signals per row.",
    running: `${formatNumber(finished)} rows have verified verdicts. Sources and checkpoints are saved as checks finish.`,
    pausing: "Saving in-flight checks. Remote TinySet work remains available to resume.",
    paused: "Your checkpoints are saved. Resume the same audit to keep your progress.",
    complete: `${formatNumber(audit.total)} original rows retained. Inspect the sources or export your list.`,
    needs_review: `${formatNumber(review)} rows need evidence review. This run has not passed the full-completion gate.`,
    error: audit.error || "Saved progress remains available. Inspect the activity log before resuming.",
  };
  $("progressDescription").textContent = descriptions[audit.status] || "Inspect the evidence and activity log.";
  $("progressPercent").textContent = `${percent}%`;
  $("progressFill").style.width = `${percent}%`;
  $("progressBar").setAttribute("aria-valuenow", percent);
  $("progressBar").setAttribute("aria-valuetext", `${checked} of ${audit.total} rows have four or more checks; ${finished} verified verdicts`);
  $("reviewCountLabel").textContent = review ? `${formatNumber(review)} rows awaiting review` : "No rows awaiting review";
  $("budgetLabel").textContent = `${money(audit.reserved)} reserved / ${money(audit.budget)} paid usage cap`;
  $("reviewFilterCount").textContent = formatNumber(review);
  $("runAudit").hidden = !["ready", "paused", "error"].includes(audit.status);
  $("runAudit").innerHTML = audit.status === "ready" ? 'Start audit <span aria-hidden="true">→</span>' : 'Resume audit <span aria-hidden="true">→</span>';
  $("runAudit").disabled = !state.config?.key_configured;
  $("pauseAudit").hidden = !["running", "pausing"].includes(audit.status);
  $("pauseAudit").disabled = audit.status === "pausing";
  $("exportCsv").disabled = !audit.total;
  const notice = $("auditNotice");
  notice.hidden = true;
  notice.className = "audit-notice";
  if (audit.error) {
    notice.textContent = audit.error;
    notice.classList.add("error"); notice.hidden = false;
  } else if (audit.status === "needs_review") {
    notice.textContent = "This list still has unresolved evidence. Export includes review flags and any blank verdicts so no row is silently classified. Open a row to inspect its sources.";
    notice.hidden = false;
  } else if (audit.total < 500) {
    notice.textContent = `Pilot list: ${formatNumber(audit.total)} rows. The bounty’s scale requirement needs a verified run on at least 500 real rows.`;
    notice.hidden = false;
  }
  renderTable();
  if (state.selectedRowId) renderDrawer(state.selectedRowId);
}

function verdictPill(result, status) {
  const verdict = result?.verdict;
  if (verdict === "alive") return '<span class="pill pill-alive"><i class="dot green"></i>Alive</span>';
  if (verdict === "slowing down") return '<span class="pill pill-slowing"><i class="dot amber"></i>Slowing down</span>';
  if (verdict === "zombie") return '<span class="pill pill-zombie"><i class="dot red"></i>Zombie</span>';
  if (status === "pending") return '<span class="pill pill-neutral">Pending</span>';
  if (status === "checking") return '<span class="pill pill-neutral">Checking…</span>';
  return '<span class="pill pill-review">Needs evidence</span>';
}

function filteredRows() {
  return state.rows.filter((row) => {
    const result = row.result || {};
    if (state.filter === "review" && !(row.status === "review" || result.review_required)) return false;
    if (!["all", "review"].includes(state.filter) && result.verdict !== state.filter) return false;
    if (state.search && ![row.name, row.website, ...(row.original || [])].join(" ").toLowerCase().includes(state.search)) return false;
    return true;
  });
}

function renderTable() {
  const audit = state.audit;
  if (!audit) return;
  const rows = filteredRows();
  const pages = Math.max(1, Math.ceil(rows.length / state.pageSize));
  state.page = Math.max(0, Math.min(state.page, pages - 1));
  const start = state.page * state.pageSize;
  const visible = rows.slice(start, start + state.pageSize);
  $("tableRowCount").textContent = formatNumber(audit.total);
  $("resultsHead").innerHTML = '<tr><th scope="col">#</th><th scope="col">' + (isJobMode() ? 'JOB / EMPLOYER' : 'COMPANY / ORIGINAL INPUT') + '</th><th scope="col">VERDICT</th><th scope="col">LATEST ACTIVITY</th><th scope="col">FIVE SIGNALS</th><th scope="col">EVIDENCE</th><th scope="col">CONFIDENCE</th><th scope="col"><span class="sr-only">Inspect</span></th></tr>';
  $("resultsBody").innerHTML = visible.map((row) => {
    const result = row.result || {};
    const displayName = rowDisplayName(row);
    const displayUrl = rowDisplayUrl(row);
    const employer = rowEmployer(row);
    const signals = result.signals || {};
    const signalsHtml = signalKinds.map((kind) => {
      const signal = signals[kind] || {};
      const style = signal.status === "active" && signal.verified ? "active" : ["inactive", "not_found"].includes(signal.status) && signal.verified ? "inactive" : signal.status === "blocked" ? "blocked" : "";
      return `<span class="signal-indicator ${style}" title="${esc(`${activeSignalLabels()[kind]}: ${signal.status || "pending"}${signal.verified ? " · verified" : ""}`)}"></span>`;
    }).join("");
    const sourceCount = new Set(result.evidence_links || []).size;
    return `<tr tabindex="0" data-row="${esc(row.row_id)}" aria-label="Inspect ${esc(displayName || `row ${row.position + 1}`)}"><td>${String(row.position + 1).padStart(3, "0")}</td><td><div class="company-cell${isJobMode() ? " job-title-cell" : ""}"><span class="company-avatar" aria-hidden="true">${esc((displayName || "?").slice(0, 2).toUpperCase())}</span><div><strong title="${esc(displayName)}">${esc(displayName || "Unnamed company")}</strong><small title="${esc(displayUrl)}">${esc(isJobMode() ? [employer, displayUrl].filter(Boolean).join(" · ") : domain(displayUrl))}</small></div></div></td><td>${verdictPill(result, row.status)}${result.review_required && result.verdict ? '<span class="pill pill-review" title="Evidence review still required">Review</span>' : ""}</td><td class="date-cell">${result.latest_activity_date ? esc(dateLabel(result.latest_activity_date)) : '<span title="A source activity date has not been verified">—</span>'}</td><td><div class="signal-dots" aria-label="${esc(`${result.signals_verified || 0} verified signals; ${result.signals_checked || 0} checked`)}">${signalsHtml}</div></td><td><span class="evidence-count"><span aria-hidden="true">⌁</span>${sourceCount ? `${sourceCount} sources` : "—"}</span></td><td class="confidence-cell">${esc(result.confidence ? result.confidence[0].toUpperCase() + result.confidence.slice(1) : "—")}</td><td class="row-arrow" aria-hidden="true">↗</td></tr>`;
  }).join("");
  $("resultsBody").querySelectorAll("[data-row]").forEach((row) => {
    row.addEventListener("click", () => openDrawer(row.dataset.row, row));
    row.addEventListener("keydown", (event) => {
      if (["Enter", " "].includes(event.key)) { event.preventDefault(); openDrawer(row.dataset.row, row); }
    });
  });
  $("tableEmpty").hidden = visible.length > 0;
  $("pageRange").textContent = rows.length ? `Showing ${formatNumber(start + 1)}–${formatNumber(start + visible.length)} of ${formatNumber(rows.length)}${rows.length < audit.total ? " matching" : ""} rows` : "0 matching rows";
  $("pageNumber").textContent = `${state.page + 1} / ${pages}`;
  $("prevPage").disabled = state.page === 0;
  $("nextPage").disabled = state.page >= pages - 1;
}

function setFilter(filter) {
  state.filter = filter;
  state.page = 0;
  document.querySelectorAll("[data-filter]").forEach((button) => {
    const active = button.dataset.filter === filter;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active);
  });
  renderTable();
}

async function runAudit() {
  if (!state.audit) return;
  const id = state.audit.id;
  $("runAudit").disabled = true;
  try {
    state.audit = await post(`/api/audits/${id}/start`);
    renderAudit();
    toast("Audit started. Sources and progress will appear as checks finish.");
  } catch (error) { toast(error.message, true); }
  finally { $("runAudit").disabled = !state.config?.key_configured; }
}

async function pauseAudit() {
  if (!state.audit) return;
  $("pauseAudit").disabled = true;
  try {
    state.audit = await post(`/api/audits/${state.audit.id}/pause`);
    renderAudit();
    toast("Pause requested. In-flight work is being saved.");
  } catch (error) { toast(error.message, true); $("pauseAudit").disabled = false; }
}

async function refresh() {
  if (!state.audit || state.refreshing || document.hidden) return;
  if (!["running", "pausing"].includes(state.audit.status)) return;
  state.refreshing = true;
  const generation = state.generation;
  const id = state.audit.id;
  try {
    const [audit, rows] = await Promise.all([api(`/api/audits/${id}`), loadAllRows(id, generation)]);
    if (generation !== state.generation || rows === null) return;
    const wasRunning = ["running", "pausing"].includes(state.audit.status);
    state.audit = audit; state.rows = rows;
    state.audits = state.audits.map((a) => a.id === id ? audit : a);
    renderAudit(); renderAuditList();
    await loadEvents();
    if (wasRunning && !["running", "pausing"].includes(audit.status)) {
      toast(audit.status === "complete" ? "Audit complete. Every original row has a verified verdict." : audit.status === "paused" ? "Progress saved. Resume whenever you are ready." : "Checks saved. Inspect the remaining reviews and run report.");
    }
  } catch (error) { toast(error.message, true); }
  finally { state.refreshing = false; }
}

async function loadEvents() {
  if (!state.audit) return;
  const id = state.audit.id;
  try {
    const data = await api(`/api/audits/${id}/events`);
    if (state.audit?.id !== id) return;
    $("activityList").innerHTML = (data.events || []).map((event) => `<div class="activity-row"><time datetime="${esc(event.time)}">${esc(new Date(event.time).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }))}</time><span class="activity-kind">${esc(event.kind)}</span><p>${esc(event.message)}</p></div>`).join("") || '<p class="help-small">Audit events will appear here.</p>';
  } catch (error) { toast(error.message, true); }
}

function sourceLink(url) {
  const href = linkUrl(url);
  return href ? `<a class="source-link" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(url)} <span aria-hidden="true">↗</span></a>` : '<span class="source-link">No valid source URL returned</span>';
}

function renderDrawer(rowId) {
  const row = state.rows.find((r) => r.row_id === rowId);
  if (!row) return;
  const result = row.result || {};
  const displayName = rowDisplayName(row);
  const displayUrl = rowDisplayUrl(row);
  const employer = rowEmployer(row);
  const identity = result.identity || {};
  $("drawerTitle").textContent = displayName || "Unnamed company";
  const href = linkUrl(displayUrl);
  $("drawerWebsite").textContent = displayUrl || "No original website supplied";
  if (href) $("drawerWebsite").href = href;
  else $("drawerWebsite").removeAttribute("href");
  const identityStatus = String(identity.status || "Not checked").replace(/_/g, " ");
  const originalCells = (state.audit?.headers || []).map((heading, index) => `<div><dt>${esc(heading)}</dt><dd>${esc(row.original?.[index] ?? "")}</dd></div>`).join("");
  const cards = signalKinds.map((kind) => {
    const signal = result.signals?.[kind] || {};
    const status = signal.status ? signal.status.replace(/_/g, " ") : "pending";
    const style = signal.verified ? signal.status === "active" ? "pill-alive" : "pill-neutral" : "pill-review";
    return `<article class="evidence-card"><header><h3><span aria-hidden="true">${signalSymbols[kind]}</span>${activeSignalLabels()[kind]}</h3><span class="pill ${style}">${esc(status)}${signal.verified ? " · verified" : ""}</span></header><div class="evidence-facts"><span>ACTIVITY: ${signal.latest_date ? esc(dateLabel(signal.latest_date)) : "not established"}${signal.latest_date && !signal.date_verified ? " · unverified" : ""}</span><span>CHECKED: ${signal.checked_at ? esc(dateLabel(signal.checked_at, true)) : "pending"}</span></div><p class="evidence-note">${esc(signal.note || "This signal has not yet been checked.")}</p>${signal.quote ? `<blockquote class="evidence-quote">${esc(signal.quote)}</blockquote>` : ""}${signal.url ? sourceLink(signal.url) : '<span class="source-link">A source has not been established.</span>'}${signal.error ? `<div class="evidence-error">${esc(typeof signal.error === "object" ? JSON.stringify(signal.error) : signal.error)}</div>` : ""}${signal.method ? `<p class="drawer-small">Method: ${esc(signal.method)}</p>` : ""}</article>`;
  }).join("");
  $("drawerBody").innerHTML = `<div class="drawer-verdict">${verdictPill(result, row.status)}<span class="confidence-label">${esc(result.confidence || "Not assessed")} confidence</span></div><p class="drawer-reason">${esc(result.reason || "Research has not finished for this row.")}</p>${result.review_required || row.error ? `<div class="inline-note">${esc(row.error || "This conclusion still needs evidence review.")}</div>` : ""}<div class="drawer-section-label">${isJobMode() ? "POSTING IDENTITY" : "COMPANY IDENTITY"}</div><div class="identity-card"><header><strong>${esc(identity.current_name || employer || (isJobMode() ? "Employer" : displayName) || "Original company")}</strong><span class="pill ${identity.verified ? "pill-neutral" : "pill-review"}">${esc(identityStatus)}</span></header><p>${esc(identity.note || (identity.verified ? (isJobMode() ? "The original listing and posting identity were checked against the live source." : "The original company identity was checked against the live source.") : "Identity has not yet been established."))}</p>${identity.canonical_url ? `<p>Current destination: ${esc(identity.canonical_url)}</p>` : ""}${identity.quote ? `<blockquote class="evidence-quote">${esc(identity.quote)}</blockquote>` : ""}${identity.url ? sourceLink(identity.url) : ""}</div><div class="drawer-section-label">FIVE LIVE SIGNALS</div>${cards}${result.closure && Object.keys(result.closure).length ? `<div class="drawer-section-label">${isJobMode() ? "LISTING CLOSURE" : "CLOSURE / DISCONTINUATION"}</div><div class="identity-card"><header><strong>Closure evidence</strong><span class="pill ${result.closure.verified ? "pill-neutral" : "pill-review"}">${result.closure.verified ? "Verified" : "Not verified"}</span></header><p>${esc(result.closure.note || result.closure.status || "")}</p>${result.closure.quote ? `<blockquote class="evidence-quote">${esc(result.closure.quote)}</blockquote>` : ""}${result.closure.url ? sourceLink(result.closure.url) : ""}</div>` : ""}<div class="drawer-summary"><span>${result.signals_checked || 0} / 5 signals checked</span><span>${result.signals_verified || 0} verified</span><span>${esc(row.row_id)}</span></div><p class="drawer-small">${esc(observationLimitNote())}</p><div class="drawer-section-label">ORIGINAL SPREADSHEET CELLS</div><dl class="original-cells">${originalCells}</dl>${row.dataset_id ? `<p class="drawer-small mono">TinySet dataset: ${esc(row.dataset_id)}</p>` : ""}`;
}

function openDrawer(rowId, origin) {
  state.selectedRowId = rowId;
  state.drawerOrigin = origin;
  renderDrawer(rowId);
  $("drawerBackdrop").hidden = false;
  $("evidenceDrawer").hidden = false;
  document.body.style.overflow = "hidden";
  $("closeDrawer").focus();
}

function closeDrawer() {
  $("drawerBackdrop").hidden = true;
  $("evidenceDrawer").hidden = true;
  document.body.style.overflow = "";
  state.selectedRowId = null;
  if (state.drawerOrigin?.isConnected) state.drawerOrigin.focus({ preventScroll: true });
  state.drawerOrigin = null;
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = filename;
  document.body.append(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function exportCsv() {
  if (!state.audit) return;
  $("exportCsv").disabled = true;
  try {
    const blob = await api(`/api/audits/${state.audit.id}/export`, { blob: true });
    downloadBlob(blob, `${state.audit.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-zombie-check.csv`);
    toast("CSV exported with every original row and the evidence columns.");
  } catch (error) { toast(error.message, true); }
  finally { $("exportCsv").disabled = false; }
}

async function showReport() {
  if (!state.audit) return;
  loading(true, "Checking the run’s completion gates…");
  try {
    state.report = await api(`/api/audits/${state.audit.id}/report`);
    const report = state.report;
    const labels = { at_least_500_rows: "At least 500 real input rows", all_rows_have_verdicts: "Every row has a verdict", four_live_checks_every_row: "Four live checks for every row", no_unresolved_reviews: "No unresolved evidence reviews", tinyset_used: "TinySet performed work", original_rows_preserved: "Original rows preserved" };
    $("reportBody").innerHTML = `<div class="report-banner${report.submission_ready ? " ready" : ""}"><strong>${report.submission_ready ? "The run’s completion gates passed." : "This run is not ready to claim full completion."}</strong><br>${report.submission_ready ? "Inspect the source evidence and the remaining submission requirements before submitting." : "The checks below show exactly what remains unproved. No partial result is reported as a complete audit."}</div><div class="report-gates">${Object.entries(report.gates || {}).map(([key, passed]) => `<div class="report-gate"><span>${esc(labels[key] || key.replace(/_/g, " "))}</span><span class="gate-status ${passed ? "pass" : "fail"}"><span aria-hidden="true">${passed ? "✓" : "○"}</span>${passed ? "PASS" : "PENDING"}</span></div>`).join("")}</div><div class="drawer-section-label">ACTUAL SERVICE USAGE</div>${(report.services || []).map((service) => `<div class="service-row"><strong>${esc(service.service)}</strong><span>${formatNumber(service.requests)} successful requests · ${formatNumber(service.units)} units</span></div>`).join("") || '<p class="help-small">No successful research service calls are recorded yet.</p>'}<div class="drawer-section-label">PRESERVATION & PAID USAGE CAP</div><div class="service-row"><strong>Input → output rows</strong><span>${formatNumber(report.input_rows)} → ${formatNumber(report.output_rows)}</span></div><div class="service-row"><strong>Reserved / paid usage cap</strong><span>${money(report.reserved_usd)} / ${money(report.paid_budget_usd)}</span></div><div class="drawer-section-label">WHAT THE OBSERVATIONS MEAN</div><ul class="report-notes">${(report.notes || []).map((note) => `<li>${esc(note)}</li>`).join("")}</ul><p class="report-id">Input SHA-256: ${esc(report.input_sha256 || "unavailable")}</p>`;
    $("reportId").textContent = report.audit_id.slice(0, 8);
    $("reportDialog").showModal();
  } catch (error) { toast(error.message, true); }
  finally { loading(false); }
}

function trapDrawerFocus(event) {
  if ($("evidenceDrawer").hidden || event.key !== "Tab") return;
  const focusable = [...$("evidenceDrawer").querySelectorAll('button,a[href],input,select,textarea,[tabindex="0"]')].filter((node) => !node.disabled && node.offsetParent !== null);
  if (!focusable.length) return;
  const first = focusable[0], last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

$("dropZone").addEventListener("click", () => $("fileInput").click());
$("dropZone").addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); $("fileInput").click(); } });
$("dropZone").addEventListener("dragover", (event) => { event.preventDefault(); $("dropZone").classList.add("dragging"); });
$("dropZone").addEventListener("dragleave", () => $("dropZone").classList.remove("dragging"));
$("dropZone").addEventListener("drop", (event) => { event.preventDefault(); $("dropZone").classList.remove("dragging"); readFile(event.dataTransfer.files[0]); });
$("fileInput").addEventListener("change", () => readFile($("fileInput").files[0]));
$("pasteToggle").addEventListener("click", () => { $("pasteArea").hidden = !$("pasteArea").hidden; if (!$("pasteArea").hidden) $("csvText").focus(); });
$("previewPasted").addEventListener("click", () => importContent($("csvText").value, "pasted-list.csv"));
$("importForm").addEventListener("submit", createAudit);
$("importForm").querySelectorAll('[name="strategy"]').forEach((radio) => radio.addEventListener("change", updateBudgetExplanation));
$("importBudget").addEventListener("input", updateBudgetExplanation);
$("auditMode").addEventListener("change", () => updateImportMode(true));
for (const field of ["nameColumn","urlColumn","employerColumn","employerWebsiteColumn","boardTokenColumn","jobIdColumn","jobApiColumn"]) $(field).addEventListener("change", () => {
  updateMappingPreview(true);
  updateBudgetExplanation();
});
document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => $(button.dataset.close).close()));
document.querySelectorAll("dialog").forEach((dialog) => dialog.addEventListener("click", (event) => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } }));
[$("newAuditNav"), $("newAuditTop"), $("addAuditNav")].forEach((button) => button.addEventListener("click", showWelcome));
$("howItWorksNav").addEventListener("click", () => $("helpDialog").showModal());
$("connectionSettings").addEventListener("click", () => { $("accessToken").value = sessionStorage.getItem("zc-access-token") || ""; $("settingsDialog").showModal(); });
$("settingsForm").addEventListener("submit", async (event) => { event.preventDefault(); const token = $("accessToken").value; if (token) sessionStorage.setItem("zc-access-token", token); else sessionStorage.removeItem("zc-access-token"); $("settingsDialog").close(); await connect(); });
$("runAudit").addEventListener("click", runAudit);
$("pauseAudit").addEventListener("click", pauseAudit);
$("exportCsv").addEventListener("click", exportCsv);
$("viewReport").addEventListener("click", showReport);
$("downloadReport").addEventListener("click", () => { if (state.report) downloadBlob(new Blob([JSON.stringify(state.report, null, 2)], { type: "application/json" }), `zombie-check-${state.report.audit_id.slice(0, 8)}-report.json`); });
document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => setFilter(button.dataset.filter)));
$("rowSearch").addEventListener("input", (event) => { state.search = event.target.value.toLowerCase().trim(); state.page = 0; renderTable(); });
$("pageSize").addEventListener("change", (event) => { state.pageSize = Number(event.target.value); state.page = 0; renderTable(); });
$("prevPage").addEventListener("click", () => { state.page -= 1; renderTable(); });
$("nextPage").addEventListener("click", () => { state.page += 1; renderTable(); });
$("closeDrawer").addEventListener("click", closeDrawer);
$("drawerBackdrop").addEventListener("click", closeDrawer);
$("toggleActivity").addEventListener("click", async () => { const shown = $("activityList").hidden; $("activityList").hidden = !shown; $("toggleActivity").setAttribute("aria-expanded", shown); $("toggleActivity").innerHTML = `${shown ? "Hide" : "Show"} activity <span aria-hidden="true">${shown ? "⌃" : "⌄"}</span>`; if (shown) await loadEvents(); });
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !$("evidenceDrawer").hidden) closeDrawer(); trapDrawerFocus(event); });
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
setInterval(refresh, 5000);
connect();
