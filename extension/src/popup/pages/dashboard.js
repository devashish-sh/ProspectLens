// dashboard.js — ProspectLens Full Dashboard Logic

const API_BASE = "http://localhost:8000/api";

// ============================================================
// STATE
// ============================================================
let allLeads    = [];
let currentPage = 1;
const PAGE_SIZE = 50;

let filters = {
  search:  "",
  source:  "",
  status:  "",
  city:    ""
};

// ============================================================
// BACKEND STATUS
// ============================================================
async function checkBackend() {
  const badge    = document.getElementById("dash-backend-status");
  const text     = badge.querySelector(".dash-status-text");

  try {
    // Check persistent disconnected state first
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      const store = await chrome.storage.local.get("disconnected");
      if (store.disconnected) {
        badge.className = "dash-status-badge offline";
        text.textContent = "Disconnected";
        return false;
      }
    }

    const res  = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
    const data = await res.json();
    if (data.status === "ok") {
      badge.className = "dash-status-badge online";
      text.textContent = "Connected";
      return true;
    }
    throw new Error();
  } catch {
    badge.className = "dash-status-badge offline";
    text.textContent = "Offline";
    return false;
  }
}

// ============================================================
// LOAD STATS
// ============================================================
async function loadStats() {
  try {
    const res  = await fetch(`${API_BASE}/leads/stats`);
    const data = await res.json();

    document.getElementById("dash-total").textContent     = data.total_leads ?? 0;
    document.getElementById("dash-new").textContent       = data.by_status?.new ?? 0;
    document.getElementById("dash-contacted").textContent = data.by_status?.contacted ?? 0;
    document.getElementById("dash-qualified").textContent = data.by_status?.qualified ?? 0;
    document.getElementById("dash-indiamart").textContent  = data.by_source?.indiamart ?? 0;
    document.getElementById("dash-googlemaps").textContent = data.by_source?.googlemaps ?? 0;
    document.getElementById("dash-justdial").textContent   = data.by_source?.justdial ?? 0;

    // Populate city filter dropdown
    const citySelect = document.getElementById("filter-city");
    const cities     = Object.keys(data.top_cities || {});
    cities.forEach(city => {
      if (city && !citySelect.querySelector(`option[value="${city}"]`)) {
        const opt   = document.createElement("option");
        opt.value   = city;
        opt.textContent = city;
        citySelect.appendChild(opt);
      }
    });

  } catch (e) {
    console.error("Stats load failed", e);
  }
}

// ============================================================
// LOAD ALL LEADS
// ============================================================
async function loadLeads() {
  const tbody = document.getElementById("leads-tbody");
  tbody.innerHTML = `<tr><td colspan="9" class="table-loading">Loading leads...</td></tr>`;

  try {
    // Build query params from filters
    const params = new URLSearchParams({ limit: 500 });
    if (filters.search) params.set("search",      filters.search);
    if (filters.source) params.set("source_site", filters.source);
    if (filters.status) params.set("lead_status", filters.status);
    if (filters.city)   params.set("city",        filters.city);

    const res  = await fetch(`${API_BASE}/leads?${params}`);
    const data = await res.json();
    allLeads   = data.leads || [];

    document.getElementById("page-subtitle").textContent =
      `${allLeads.length} lead${allLeads.length !== 1 ? "s" : ""} found`;

    currentPage = 1;
    renderLeadsPage();

  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="9" class="table-loading">Failed to load leads. Is the backend running?</td></tr>`;
  }
}

// ============================================================
// RENDER CURRENT PAGE OF LEADS
// ============================================================
function renderLeadsPage() {
  const tbody    = document.getElementById("leads-tbody");
  const start    = (currentPage - 1) * PAGE_SIZE;
  const end      = start + PAGE_SIZE;
  const paginated = allLeads.slice(start, end);

  if (paginated.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" class="table-loading">No leads found matching the filters.</td></tr>`;
    updatePagination();
    return;
  }

  tbody.innerHTML = paginated.map(lead => `
    <tr data-lead-id="${lead.lead_id}">
      <td><input type="checkbox" class="lead-checkbox" data-id="${lead.lead_id}" /></td>

      <td>
        <div class="business-name" onclick="openLeadModal('${lead.lead_id}')">
          ${escHtml(lead.business_name)}
        </div>
        ${lead.category ? `<div class="business-sub">${escHtml(lead.category)}</div>` : ""}
      </td>

      <td>${escHtml(lead.phone || "—")}</td>
      <td>${escHtml(lead.email || "—")}</td>
      <td>${escHtml(lead.city || "—")}</td>

      <td>
        <span class="source-badge source-${lead.source_site}">
          ${sourceLabel(lead.source_site)}
        </span>
      </td>

      <td>
        <select
          class="status-select status-${lead.lead_status}"
          onchange="updateStatus('${lead.lead_id}', this.value, this)"
        >
          <option value="new"       ${lead.lead_status === "new"       ? "selected" : ""}>New</option>
          <option value="contacted" ${lead.lead_status === "contacted" ? "selected" : ""}>Contacted</option>
          <option value="qualified" ${lead.lead_status === "qualified" ? "selected" : ""}>Qualified</option>
          <option value="closed"    ${lead.lead_status === "closed"    ? "selected" : ""}>Closed</option>
        </select>
      </td>

      <td>${formatDate(lead.collected_at)}</td>

      <td>
        <button class="btn btn-danger" onclick="deleteLead('${lead.lead_id}', this)">🗑</button>
      </td>
    </tr>
  `).join("");

  updatePagination();
}

// ============================================================
// PAGINATION
// ============================================================
function updatePagination() {
  const totalPages = Math.ceil(allLeads.length / PAGE_SIZE);
  document.getElementById("page-info").textContent =
    `Page ${currentPage} of ${totalPages || 1}`;
  document.getElementById("btn-prev").disabled = currentPage <= 1;
  document.getElementById("btn-next").disabled = currentPage >= totalPages;
}

// ============================================================
// UPDATE LEAD STATUS
// ============================================================
async function updateStatus(leadId, newStatus, selectEl) {
  // Update CSS class on the select element immediately for visual feedback
  selectEl.className = `status-select status-${newStatus}`;

  try {
    await fetch(`${API_BASE}/leads/${leadId}/status`, {
      method:  "PUT",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ lead_status: newStatus })
    });
    // Update local state
    const lead = allLeads.find(l => l.lead_id === leadId);
    if (lead) lead.lead_status = newStatus;
    loadStats();
  } catch {
    alert("Failed to update status. Check backend connection.");
  }
}

// ============================================================
// DELETE LEAD
// ============================================================
async function deleteLead(leadId, btn) {
  if (!confirm("Delete this lead permanently?")) return;

  btn.textContent = "...";
  btn.disabled    = true;

  try {
    await fetch(`${API_BASE}/leads/${leadId}`, { method: "DELETE" });
    // Remove row from DOM and local state
    allLeads = allLeads.filter(l => l.lead_id !== leadId);
    renderLeadsPage();
    loadStats();
  } catch {
    btn.textContent = "🗑";
    btn.disabled    = false;
    alert("Failed to delete. Check backend connection.");
  }
}

// ============================================================
// LEAD DETAIL MODAL
// ============================================================
async function openLeadModal(leadId) {
  const overlay = document.getElementById("modal-overlay");
  const body    = document.getElementById("modal-body");
  const title   = document.getElementById("modal-business-name");

  overlay.classList.remove("hidden");
  body.innerHTML = "Loading...";

  try {
    const res  = await fetch(`${API_BASE}/leads/${leadId}`);
    const data = await res.json();
    const lead = data.lead;
    const contacts = data.contacts || [];

    title.textContent = lead.business_name;

    const phones    = contacts.filter(c => c.contact_type === "phone").map(c => c.contact_value);
    const emails    = contacts.filter(c => c.contact_type === "email").map(c => c.contact_value);
    const whatsapps = contacts.filter(c => c.contact_type === "whatsapp").map(c => c.contact_value);

    body.innerHTML = `
      ${field("Source",        sourceLabel(lead.source_site))}
      ${field("Status",        lead.lead_status)}
      ${field("Category",      lead.category)}
      ${field("Contact Person",lead.contact_person)}
      ${field("Phone",         phones.length    ? phones.map(p    => `<span class="contact-chip">📞 ${escHtml(p)}</span>`).join("") : "—")}
      ${field("WhatsApp",      whatsapps.length ? whatsapps.map(w => `<span class="contact-chip">💬 ${escHtml(w)}</span>`).join("") : "—")}
      ${field("Email",         emails.length    ? emails.map(e    => `<span class="contact-chip">✉️ ${escHtml(e)}</span>`).join("") : "—")}
      ${field("Website",       lead.website     ? `<a href="${escHtml(lead.website)}" target="_blank">${escHtml(lead.website)}</a>` : "—")}
      ${field("Address",       lead.address)}
      ${field("City",          lead.city)}
      ${field("State",         lead.state)}
      ${field("Postal Code",   lead.postal_code)}
      ${field("Listing URL",   lead.listing_url ? `<a href="${escHtml(lead.listing_url)}" target="_blank">Open →</a>` : "—")}
      ${field("Collected At",  formatDate(lead.collected_at))}
      ${field("Collection Mode", lead.collection_mode)}
    `;
  } catch {
    body.innerHTML = "Failed to load lead details.";
  }
}

function field(label, value) {
  return `
    <div class="modal-field">
      <div class="modal-field-label">${label}</div>
      <div class="modal-field-value">${value || "—"}</div>
    </div>
  `;
}

// ============================================================
// LOAD BATCHES
// ============================================================
async function loadBatches() {
  const tbody = document.getElementById("batches-tbody");
  tbody.innerHTML = `<tr><td colspan="5" class="table-loading">Loading...</td></tr>`;

  try {
    const res  = await fetch(`${API_BASE}/batches`);
    const data = await res.json();
    const batches = data.batches || [];

    if (batches.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="table-loading">No collections yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = batches.map(b => `
      <tr>
        <td>${escHtml(b.batch_name || b.search_query || "Collection")}</td>
        <td><span class="source-badge source-${b.source_site}">${sourceLabel(b.source_site)}</span></td>
        <td><span class="batch-mode-badge">${b.collection_mode}</span></td>
        <td style="color: var(--accent); font-weight: 600;">${b.successful_records ?? 0}</td>
        <td>${formatDate(b.created_at)}</td>
      </tr>
    `).join("");
  } catch {
    tbody.innerHTML = `<tr><td colspan="5" class="table-loading">Failed to load collections.</td></tr>`;
  }
}

// ============================================================
// LOAD EXPORT HISTORY
// ============================================================
async function loadExportHistory() {
  const container = document.getElementById("export-history-list");

  try {
    const res  = await fetch(`${API_BASE}/export/history`);
    const data = await res.json();
    const exports = data.exports || [];

    if (exports.length === 0) {
      container.innerHTML = `<div style="color: var(--text-muted); font-size: 12px;">No exports yet.</div>`;
      return;
    }

    container.innerHTML = exports.map(e => `
      <div class="export-history-item">
        <span>${e.export_format.toUpperCase()} — ${e.record_count} leads</span>
        <span style="color: var(--text-muted);">${formatDate(e.exported_at)}</span>
        <span style="color: var(--text-muted);">${e.file_size_kb ? e.file_size_kb + " KB" : ""}</span>
      </div>
    `).join("");
  } catch {
    container.innerHTML = `<div style="color: var(--danger);">Failed to load export history.</div>`;
  }
}

// ============================================================
// LOAD JOBS (Active Background Tasks)
// ============================================================
async function loadJobs() {
  const tbody = document.getElementById("jobs-tbody");
  try {
    const res = await fetch(`${API_BASE}/jobs`);
    const data = await res.json();
    const jobs = data.jobs || [];

    if (jobs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="tbl-empty">No background tasks found.</td></tr>`;
      return;
    }

    tbody.innerHTML = jobs.map(j => {
      const typeLabel = j.job_type === "deep_collect" ? "🔍 Deep Collect" : "🌐 Website Extract";
      const pct = j.progress_percentage ?? 0;
      
      let progressHtml = `
        <div class="progress-container-inline" style="background: rgba(255,255,255,0.05); border-radius: 4px; height: 8px; width: 100px; position: relative;">
          <div style="background: var(--btn-primary); width: ${pct}%; height: 100%; border-radius: 4px; transition: width 0.3s ease;"></div>
        </div>
        <div style="font-size: 10px; margin-top: 4px; color: var(--text-muted);">${j.records_done} of ${j.records_total} (${pct}%)</div>
      `;

      let actionButtons = "";
      if (j.status === "running") {
        actionButtons = `
          <button class="btn btn-ghost" style="padding: 2px 6px; font-size: 10px; margin-right: 4px;" onclick="controlJob('${j.job_id}', 'pause')">⏸ Pause</button>
          <button class="btn btn-danger" style="padding: 2px 6px; font-size: 10px;" onclick="controlJob('${j.job_id}', 'cancel')">⏹ Stop</button>
        `;
      } else if (j.status === "paused") {
        actionButtons = `
          <button class="btn btn-primary" style="padding: 2px 6px; font-size: 10px; margin-right: 4px;" onclick="controlJob('${j.job_id}', 'resume')">▶ Resume</button>
          <button class="btn btn-danger" style="padding: 2px 6px; font-size: 10px;" onclick="controlJob('${j.job_id}', 'cancel')">⏹ Stop</button>
        `;
      } else {
        actionButtons = `<span style="color: var(--text-dark); font-size: 11px;">—</span>`;
      }

      return `
        <tr data-job-id="${j.job_id}">
          <td style="font-size: 11px; font-family: monospace; color: var(--text-muted);">${j.job_id.substring(0, 8)}...</td>
          <td style="font-weight: 600;">${typeLabel}</td>
          <td style="font-size: 11px; font-family: monospace; color: var(--text-muted);">${j.batch_id ? j.batch_id.substring(0, 8) + '...' : '—'}</td>
          <td>${progressHtml}</td>
          <td>
            <span class="source-badge" style="background: rgba(255,255,255,0.05); color: var(--text-muted); text-transform: capitalize;">
              ${j.status}
            </span>
          </td>
          <td>${actionButtons}</td>
        </tr>
      `;
    }).join("");
  } catch {
    tbody.innerHTML = `<tr><td colspan="6" class="tbl-empty">Failed to load background tasks.</td></tr>`;
  }
}

async function controlJob(jobId, action) {
  try {
    const res = await fetch(`${API_BASE}/jobs/${jobId}/${action}`, { method: "POST" });
    if (res.ok) {
      loadJobs();
    } else {
      alert(`Failed to ${action} job`);
    }
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

async function runWebsiteEnrichment() {
  const checkedCheckboxes = document.querySelectorAll(".lead-checkbox:checked");
  let batchId = null;

  if (checkedCheckboxes.length > 0) {
    const leadId = checkedCheckboxes[0].dataset.id;
    try {
      const res = await fetch(`${API_BASE}/leads/${leadId}`);
      const data = await res.json();
      batchId = data.lead.batch_id;
    } catch {
      alert("Failed to find batch ID for the selected leads.");
      return;
    }
  } else {
    try {
      const res = await fetch(`${API_BASE}/batches`);
      const data = await res.json();
      const batches = data.batches || [];
      if (batches.length > 0) {
        if (!confirm(`No leads selected. Do you want to run Website Enrichment on the most recent collection batch: "${batches[0].batch_name}"?`)) {
          return;
        }
        batchId = batches[0].batch_id;
      } else {
        alert("No collection batches found. Please run a collection first.");
        return;
      }
    } catch {
      alert("Failed to fetch batches from backend.");
      return;
    }
  }

  try {
    const res = await fetch(`${API_BASE}/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ batch_id: batchId, job_type: "website_extract" })
    });
    const data = await res.json();
    if (res.ok) {
      alert("Website Enrichment job queued successfully! Go to Tasks to view progress.");
      showSection("jobs");
    } else {
      alert(`Failed to start enrichment: ${data.detail || "Unknown error"}`);
    }
  } catch (err) {
    alert(`Error starting enrichment: ${err.message}`);
  }
}

// ============================================================
// EXPORT
// ============================================================
async function doExport(format) {
  try {
    const res = await fetch(`${API_BASE}/export/${format}`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        source_site:  filters.source || null,
        lead_status:  filters.status || null,
        format
      })
    });

    if (!res.ok) {
      alert("Export failed — no leads found or backend offline.");
      return;
    }

    const blob     = await res.blob();
    const url      = URL.createObjectURL(blob);
    const a        = document.createElement("a");
    a.href         = url;
    a.download     = `prospectlens_export_${Date.now()}.${format}`;
    a.click();
    URL.revokeObjectURL(url);

    // Refresh export history
    loadExportHistory();
  } catch {
    alert("Export failed. Make sure the backend is running.");
  }
}

// ============================================================
// NAVIGATION
// ============================================================
function showSection(section) {
  document.getElementById("leads-section").classList.add("hidden");
  document.getElementById("batches-section").classList.add("hidden");
  document.getElementById("export-section").classList.add("hidden");
  document.getElementById("jobs-section").classList.add("hidden");
  document.getElementById("stat-cards").classList.add("hidden");
  document.getElementById("filters-bar").classList.add("hidden");

  document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("active"));

  if (section === "leads") {
    document.getElementById("leads-section").classList.remove("hidden");
    document.getElementById("stat-cards").classList.remove("hidden");
    document.getElementById("filters-bar").classList.remove("hidden");
    document.getElementById("nav-leads").classList.add("active");
    document.getElementById("page-title").textContent = "All Leads";
    loadLeads();
  }

  if (section === "batches") {
    document.getElementById("batches-section").classList.remove("hidden");
    document.getElementById("nav-batches").classList.add("active");
    document.getElementById("page-title").textContent = "Collections";
    document.getElementById("page-subtitle").textContent = "All past collection sessions";
    loadBatches();
  }

  if (section === "jobs") {
    document.getElementById("jobs-section").classList.remove("hidden");
    document.getElementById("nav-jobs").classList.add("active");
    document.getElementById("page-title").textContent = "Tasks";
    document.getElementById("page-subtitle").textContent = "Background collection & enrichment tasks";
    loadJobs();
  }

  if (section === "export") {
    document.getElementById("export-section").classList.remove("hidden");
    document.getElementById("nav-export").classList.add("active");
    document.getElementById("page-title").textContent = "Export";
    document.getElementById("page-subtitle").textContent = "Download your leads";
    loadExportHistory();
  }
}

// ============================================================
// UTILITY HELPERS
// ============================================================
function escHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function sourceLabel(source) {
  const labels = {
    indiamart:  "IndiaMART",
    googlemaps: "G Maps",
    justdial:   "Justdial"
  };
  return labels[source] || source || "—";
}

function formatDate(dateStr) {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return dateStr;
  }
}

// ============================================================
// INIT
// ============================================================
async function init() {
  await checkBackend();
  await loadStats();

  // Navigation
  document.getElementById("nav-leads").addEventListener("click",   () => showSection("leads"));
  document.getElementById("nav-batches").addEventListener("click", () => showSection("batches"));
  document.getElementById("nav-jobs").addEventListener("click",    () => showSection("jobs"));
  document.getElementById("nav-export").addEventListener("click",  () => showSection("export"));

  // Filters
  let searchTimer;
  document.getElementById("filter-search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      filters.search = e.target.value.trim();
      currentPage = 1;
      loadLeads();
    }, 400);
  });

  document.getElementById("filter-source").addEventListener("change", (e) => {
    filters.source = e.target.value;
    currentPage = 1;
    loadLeads();
  });

  document.getElementById("filter-status").addEventListener("change", (e) => {
    filters.status = e.target.value;
    currentPage = 1;
    loadLeads();
  });

  document.getElementById("filter-city").addEventListener("change", (e) => {
    filters.city = e.target.value;
    currentPage = 1;
    loadLeads();
  });

  document.getElementById("btn-clear-filters").addEventListener("click", () => {
    filters = { search: "", source: "", status: "", city: "" };
    document.getElementById("filter-search").value  = "";
    document.getElementById("filter-source").value  = "";
    document.getElementById("filter-status").value  = "";
    document.getElementById("filter-city").value    = "";
    currentPage = 1;
    loadLeads();
  });

  // Pagination
  document.getElementById("btn-prev").addEventListener("click", () => {
    if (currentPage > 1) { currentPage--; renderLeadsPage(); }
  });

  document.getElementById("btn-next").addEventListener("click", () => {
    const totalPages = Math.ceil(allLeads.length / PAGE_SIZE);
    if (currentPage < totalPages) { currentPage++; renderLeadsPage(); }
  });

  // Export buttons in header
  document.getElementById("btn-export-xlsx").addEventListener("click", () => doExport("xlsx"));
  document.getElementById("btn-export-csv").addEventListener("click",  () => doExport("csv"));

  // Export buttons in export panel
  document.querySelectorAll(".export-btn").forEach(btn => {
    btn.addEventListener("click", () => doExport(btn.dataset.format));
  });

  // Modal close
  document.getElementById("modal-close").addEventListener("click", () => {
    document.getElementById("modal-overlay").classList.add("hidden");
  });
  document.getElementById("modal-overlay").addEventListener("click", (e) => {
    if (e.target === document.getElementById("modal-overlay")) {
      document.getElementById("modal-overlay").classList.add("hidden");
    }
  });

  // Select all checkbox
  document.getElementById("select-all").addEventListener("change", (e) => {
    document.querySelectorAll(".lead-checkbox").forEach(cb => cb.checked = e.target.checked);
  });

  // Background jobs refresh and website enrichment
  document.getElementById("btn-refresh-jobs").addEventListener("click", loadJobs);
  document.getElementById("btn-enrich-websites").addEventListener("click", runWebsiteEnrichment);

  // Load section based on URL hash if present, default to leads
  const hash = window.location.hash.substring(1);
  if (["leads", "batches", "jobs", "export"].includes(hash)) {
    showSection(hash);
  } else {
    showSection("leads");
  }
}

// Expose functions needed by inline onclick handlers
window.updateStatus    = updateStatus;
window.deleteLead      = deleteLead;
window.openLeadModal   = openLeadModal;
window.controlJob      = controlJob;

document.addEventListener("DOMContentLoaded", init);