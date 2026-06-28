// popup.js — ProspectLens Extension Popup Logic
//
// This file runs every time the popup opens.
// It handles:
// 1. Checking if the backend is running
// 2. Detecting which supported site the user is on
// 3. Showing live lead stats from the database
// 4. Starting a collection when the user clicks "Collect"
// 5. Showing recent collection batches

const API_BASE = "http://localhost:8000/api";

// ============================================================
// MODE DESCRIPTIONS
// ============================================================
const MODE_DESCRIPTIONS = {
  quick: "Collects visible listings on current page. Fast, no page navigation.",
  deep:  "Visits each listing page individually. Slower but gets phones, emails, and websites."
};

// ============================================================
// SITE DETECTION
// Maps URL patterns to display names and icons
// ============================================================
const SUPPORTED_SITES = [
  { pattern: "indiamart.com",   name: "IndiaMART",    icon: "🏭" },
  { pattern: "google.com/maps", name: "Google Maps",  icon: "🗺️" },
  { pattern: "maps.google.com", name: "Google Maps",  icon: "🗺️" },
  { pattern: "justdial.com",    name: "Justdial",     icon: "📞" },
];

function detectSite(url) {
  for (const site of SUPPORTED_SITES) {
    if (url.includes(site.pattern)) return site;
  }
  return null;
}

// ============================================================
// BACKEND STATUS CHECK
// ============================================================
async function checkBackendStatus() {
  const badge    = document.getElementById("backend-status");
  const dotText  = badge.querySelector(".status-text");

  try {
    const res  = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
    const data = await res.json();

    if (data.status === "ok") {
      badge.className    = "status-badge status-online";
      dotText.textContent = "Connected";
      return true;
    } else {
      throw new Error("degraded");
    }
  } catch {
    badge.className    = "status-badge status-offline";
    dotText.textContent = "Offline";
    return false;
  }
}

// ============================================================
// LOAD STATS FROM BACKEND
// ============================================================
async function loadStats() {
  try {
    const res  = await fetch(`${API_BASE}/leads/stats`);
    const data = await res.json();

    document.getElementById("stat-total").textContent = data.total_leads ?? 0;
    document.getElementById("stat-new").textContent   = data.by_status?.new ?? 0;

    // Count today's leads from batches
    const batchRes  = await fetch(`${API_BASE}/batches`);
    const batchData = await batchRes.json();

    const today = new Date().toISOString().split("T")[0];
    const todayCount = (batchData.batches || [])
      .filter(b => b.created_at && b.created_at.startsWith(today))
      .reduce((sum, b) => sum + (b.successful_records || 0), 0);

    document.getElementById("stat-today").textContent = todayCount;
  } catch {
    // Backend offline — stats stay as —
  }
}

// ============================================================
// LOAD RECENT BATCHES
// ============================================================
async function loadRecentBatches() {
  const container = document.getElementById("recent-batches");

  try {
    const res  = await fetch(`${API_BASE}/batches`);
    const data = await res.json();
    const batches = (data.batches || []).slice(0, 3);

    if (batches.length === 0) {
      container.innerHTML = '<div class="empty-state">No collections yet</div>';
      return;
    }

    container.innerHTML = batches.map(b => `
      <div class="batch-item">
        <span class="batch-name">${b.batch_name || b.search_query || "Collection"}</span>
        <span class="batch-count">${b.successful_records || 0} leads</span>
      </div>
    `).join("");

  } catch {
    container.innerHTML = '<div class="empty-state">Backend offline</div>';
  }
}

// ============================================================
// MODE SELECTOR
// ============================================================
let currentMode = "quick";

function setupModeSelector() {
  const quickBtn = document.getElementById("mode-quick");
  const deepBtn  = document.getElementById("mode-deep");
  const modeDesc = document.getElementById("mode-desc");

  quickBtn.addEventListener("click", () => {
    currentMode = "quick";
    quickBtn.classList.add("active");
    deepBtn.classList.remove("active");
    modeDesc.textContent = MODE_DESCRIPTIONS.quick;
  });

  deepBtn.addEventListener("click", () => {
    currentMode = "deep";
    deepBtn.classList.add("active");
    quickBtn.classList.remove("active");
    modeDesc.textContent = MODE_DESCRIPTIONS.deep;
  });
}

// ============================================================
// START COLLECTION
// Sends a message to collector.js running on the active tab
// ============================================================
async function startCollection(site) {
  const collectBtn      = document.getElementById("collect-btn");
  const progressContainer = document.getElementById("progress-container");
  const progressFill    = document.getElementById("progress-fill");
  const progressText    = document.getElementById("progress-text");

  // Disable button and show running state
  collectBtn.disabled = true;
  collectBtn.classList.add("running");
  collectBtn.querySelector(".collect-btn-text").textContent = "Collecting...";
  progressContainer.classList.remove("hidden");
  progressFill.style.width = "5%";
  progressText.textContent = "Starting collection...";

  try {
    // Step 1 — Create a batch in the backend
    const batchRes = await fetch(`${API_BASE}/batches`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        search_query:    document.title || site.name,
        source_site:     site.name.toLowerCase().replace(" ", ""),
        collection_mode: currentMode
      })
    });

    const batchData = await batchRes.json();
    const batchId   = batchData.batch_id;

    progressFill.style.width = "15%";
    progressText.textContent = "Batch created — injecting collector...";

    // Step 2 — Send message to content script
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    chrome.tabs.sendMessage(tab.id, {
      action:   "START_COLLECTION",
      mode:     currentMode,
      batch_id: batchId,
      site:     site.name
    }, (response) => {
      if (chrome.runtime.lastError) {
        progressText.textContent = "Error: Could not reach page. Refresh and try again.";
        resetCollectButton();
        return;
      }

      if (response && response.status === "started") {
        progressFill.style.width = "30%";
        progressText.textContent = `Collecting from ${site.name}...`;
      }
    });

    // Step 3 — Listen for progress updates from content script
    chrome.runtime.onMessage.addListener(function progressListener(msg) {
      if (msg.action === "COLLECTION_PROGRESS") {
        const pct = Math.round((msg.done / msg.total) * 100);
        progressFill.style.width = `${pct}%`;
        progressText.textContent = `${msg.done} of ${msg.total} leads collected`;
      }

      if (msg.action === "COLLECTION_COMPLETE") {
        progressFill.style.width = "100%";
        progressText.textContent = `✅ Done — ${msg.saved} leads saved, ${msg.duplicates} duplicates skipped`;
        chrome.runtime.onMessage.removeListener(progressListener);

        // Update batch record with final counts
        fetch(`${API_BASE}/batches/${batchId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            total_records:      msg.total,
            successful_records: msg.saved,
            failed_records:     msg.failed || 0
          })
        });

        // Reload stats and batches after 1 second
        setTimeout(() => {
          loadStats();
          loadRecentBatches();
          resetCollectButton();
        }, 2000);
      }

      if (msg.action === "COLLECTION_ERROR") {
        progressText.textContent = `❌ Error: ${msg.message}`;
        resetCollectButton();
        chrome.runtime.onMessage.removeListener(progressListener);
      }
    });

  } catch (err) {
    progressText.textContent = `❌ Backend error: ${err.message}`;
    resetCollectButton();
  }
}

function resetCollectButton() {
  const collectBtn = document.getElementById("collect-btn");
  collectBtn.disabled = false;
  collectBtn.classList.remove("running");
  collectBtn.querySelector(".collect-btn-text").textContent = "Start Collection";
}

// ============================================================
// EXPORT BUTTON
// ============================================================
async function handleExport() {
  try {
    const res = await fetch(`${API_BASE}/export/xlsx`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });

    if (res.ok) {
      // Trigger file download
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href     = url;
      a.download = `prospectlens_export_${Date.now()}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } else {
      alert("Export failed — no leads found or backend offline.");
    }
  } catch {
    alert("Backend is offline. Start it first.");
  }
}

// ============================================================
// MAIN INIT — runs when popup opens
// ============================================================
async function init() {
  // 1. Check backend
  const isOnline = await checkBackendStatus();

  // 2. Detect current site
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const site  = tab?.url ? detectSite(tab.url) : null;

  // 3. Show correct banner
  if (site) {
    document.getElementById("page-banner").classList.remove("hidden");
    document.getElementById("page-icon").textContent = site.icon;
    document.getElementById("page-name").textContent = site.name;
    document.getElementById("collection-panel").classList.remove("hidden");
  } else {
    document.getElementById("unsupported-banner").classList.remove("hidden");
  }

  // 4. Load stats and batches if backend is online
  if (isOnline) {
    loadStats();
    loadRecentBatches();
  }

  // 5. Setup mode selector
  setupModeSelector();

  // 6. Collect button
  document.getElementById("collect-btn").addEventListener("click", () => {
    if (!isOnline) {
      alert("Backend is offline. Start it with: uvicorn main:app --reload --port 8000");
      return;
    }
    if (site) startCollection(site);
  });

  // 7. Export button
  document.getElementById("btn-export").addEventListener("click", handleExport);

  // 8. Settings button (placeholder for now)
  document.getElementById("btn-settings").addEventListener("click", () => {
    alert("Settings coming in a future update.");
  });
}

// Run on popup open
document.addEventListener("DOMContentLoaded", init);


document.getElementById("open-dashboard").addEventListener("click", () => {
    chrome.tabs.create({ url: chrome.runtime.getURL("src/popup/pages/dashboard.html") });
  });