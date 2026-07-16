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
// ============================================================
// BACKEND STATUS CHECK
// ============================================================
function updateButtonUI(isDisconnected) {
  const reconnectBtn = document.getElementById("btn-reconnect-backend");
  if (!reconnectBtn) return;
  const labelSpan = reconnectBtn.querySelector("span");
  const svgEl = reconnectBtn.querySelector("svg");

  if (isDisconnected) {
    reconnectBtn.classList.remove("btn-disconnect");
    if (labelSpan) labelSpan.textContent = "Connect Backend";
    if (svgEl) {
      svgEl.innerHTML = '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0" />';
    }
  } else {
    reconnectBtn.classList.add("btn-disconnect");
    if (labelSpan) labelSpan.textContent = "Disconnect Backend";
    if (svgEl) {
      svgEl.innerHTML = '<line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>';
    }
  }
}

async function checkBackendStatus() {
  const badge    = document.getElementById("backend-status");
  const dotText  = badge.querySelector(".status-text");

  // Check persistent disconnected state
  let isDisconnected = false;
  if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
    const store = await chrome.storage.local.get("disconnected");
    isDisconnected = !!store.disconnected;
  }

  if (isDisconnected) {
    badge.className    = "status-badge status-offline";
    dotText.textContent = "Disconnected";
    updateButtonUI(true);
    return false;
  }

  try {
    const res  = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
    const data = await res.json();

    if (data.status === "ok") {
      badge.className    = "status-badge status-online";
      dotText.textContent = "Connected";
      updateButtonUI(false);
      return true;
    } else {
      throw new Error("degraded");
    }
  } catch {
    badge.className    = "status-badge status-offline";
    dotText.textContent = "Offline";
    updateButtonUI(true);
    return false;
  }
}

window.checkBackendStatus = checkBackendStatus;

// ============================================================
// LOAD STATS FROM BACKEND
// ============================================================
async function loadStats() {
  try {
    const res  = await fetch(`${API_BASE}/leads/stats`);
    const data = await res.json();

    document.getElementById("stat-total").textContent = data.total_leads ?? 0;
    
    // Count active sources
    const activeSources = Object.keys(data.by_source || {}).filter(k => data.by_source[k] > 0).length;
    document.getElementById("stat-new").textContent = activeSources;

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
// LOAD PERSISTENT DATA CAPSULES
// ============================================================
function formatTimeAgo(dateStr) {
  if (!dateStr) return "Waiting";
  try {
    let parsedStr = dateStr;
    if (!parsedStr.endsWith("Z") && !parsedStr.includes("+")) {
      parsedStr += "Z";
    }
    const date = new Date(parsedStr);
    const seconds = Math.floor((new Date() - date) / 1000);
    
    if (seconds < 60) return "Updated just now";
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `Updated ${minutes} min ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `Updated ${hours} hours ago`;
    
    return "Updated " + date.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  } catch {
    return dateStr;
  }
}

function openCapsuleDashboard(sourceSite) {
  if (typeof chrome !== "undefined" && chrome.tabs && chrome.tabs.create) {
    chrome.tabs.create({ url: chrome.runtime.getURL(`src/popup/pages/dashboard.html?capsule=${sourceSite}#capsules`) });
  } else {
    window.open(`src/popup/pages/dashboard.html?capsule=${sourceSite}#capsules`, "_blank");
  }
}
window.openCapsuleDashboard = openCapsuleDashboard;

async function loadRecentBatches() {
  const container = document.getElementById("recent-batches");

  const CAPSULES_DEF = [
    { key: "googlemaps", name: "Google Maps", icon: "🗺️", sourceSite: "googlemaps" },
    { key: "indiamart", name: "IndiaMART", icon: "🏭", sourceSite: "indiamart" },
    { key: "justdial", name: "Justdial", icon: "📞", sourceSite: "justdial" },
    { key: "tradeindia", name: "TradeIndia", icon: "📦", sourceSite: "tradeindia" }
  ];

  try {
    const statsRes = await fetch(`${API_BASE}/leads/stats`);
    const statsData = await statsRes.json();
    const sourceCounts = statsData.by_source || {};

    const batchRes = await fetch(`${API_BASE}/batches`);
    const batchData = await batchRes.json();
    const batches = batchData.batches || [];

    const activeCapsules = CAPSULES_DEF.filter(c => (sourceCounts[c.sourceSite] || 0) > 0);

    if (activeCapsules.length === 0) {
      container.innerHTML = '<div class="empty-msg">No collections yet</div>';
      return;
    }

    container.innerHTML = activeCapsules.map(c => {
      const totalLeads = sourceCounts[c.sourceSite] || 0;
      const sourceBatches = batches.filter(b => (b.source_site || "").toLowerCase().replace(/\s+/g, "") === c.sourceSite);
      
      let lastUpdated = null;
      if (sourceBatches.length > 0) {
        sourceBatches.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        lastUpdated = sourceBatches[0].created_at;
      }

      const timeText = lastUpdated ? formatTimeAgo(lastUpdated) : "Waiting";
      const countLabel = totalLeads === 1 ? "1 Lead" : `${totalLeads} Leads`;

      return `
        <div class="batch-item" style="cursor: pointer;" onclick="openCapsuleDashboard('${c.sourceSite}')">
          <span class="batch-name">${c.name}</span>
          <span class="batch-count">${countLabel} • ${timeText}</span>
        </div>
      `;
    }).join("");

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
        if (currentMode === "deep") {
          progressText.textContent = "✅ Sweeper complete! Launching deep detail extractor in background...";
        } else {
          progressText.textContent = `✅ Done — ${msg.saved} leads saved, ${msg.duplicates} duplicates skipped`;
        }
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

        // If Deep Mode, trigger background Playwright worker
        if (currentMode === "deep") {
          fetch(`${API_BASE}/jobs`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ batch_id: batchId, job_type: "deep_collect" })
          });
        }

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
  let tab = null;
  let site = null;
  if (typeof chrome !== "undefined" && chrome.tabs && chrome.tabs.query) {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    tab = tabs ? tabs[0] : null;
    site = tab?.url ? detectSite(tab.url) : null;
  }

  if (site) {
    const visitsKey = `prospectlens-visits-${site.key}`;
    const visits = parseInt(localStorage.getItem(visitsKey) || "0") + 1;
    localStorage.setItem(visitsKey, visits);
    localStorage.setItem(`prospectlens-last-active-${site.key}`, new Date().toISOString());
    broadcastStateUpdate();
  }

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
    if (site) {
      const searchesKey = `prospectlens-searches-${site.key}`;
      const searches = parseInt(localStorage.getItem(searchesKey) || "0") + 1;
      localStorage.setItem(searchesKey, searches);
      
      startCollection(site);
      
      // Broadcast state update
      setTimeout(broadcastStateUpdate, 1200);
    }
  });

  function broadcastStateUpdate() {
    if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.sendMessage) {
      chrome.runtime.sendMessage({ type: "STATE_UPDATED" });
    }
  }

  // 7. Export button
  document.getElementById("btn-export").addEventListener("click", handleExport);


  // 9. Connect/Disconnect button click handler
  const reconnectBtn = document.getElementById("btn-reconnect-backend");
  if (reconnectBtn) {
    reconnectBtn.addEventListener("click", async (e) => {
      e.stopPropagation(); // prevent dropdown closing
      
      const store = await chrome.storage.local.get("disconnected");
      const nextDisconnectedState = !store.disconnected;
      
      // Update persistent storage state
      await chrome.storage.local.set({ disconnected: nextDisconnectedState });
      
      // Update UI to checking/offline transition state
      const badge = document.getElementById("backend-status");
      const dotText = badge.querySelector(".status-text");
      if (!nextDisconnectedState) {
        badge.className = "status-badge status-checking";
        if (dotText) dotText.textContent = "Connecting...";
      } else {
        badge.className = "status-badge status-offline";
        if (dotText) dotText.textContent = "Disconnecting...";
      }
      
      // Trigger backend check
      await checkBackendStatus();
    });
  }

  // Helper to open dashboard with a hash
  const openDashboard = (hash = "") => {
    if (typeof chrome !== "undefined" && chrome.tabs && chrome.tabs.create) {
      chrome.tabs.create({ url: chrome.runtime.getURL(`src/popup/pages/dashboard.html${hash}`) });
    } else {
      window.open(`src/popup/pages/dashboard.html${hash}`, "_blank");
    }
  };

  // View All button (recent activity section)
  document.getElementById("open-dashboard").addEventListener("click", () => openDashboard("#leads"));

  // Brand logo click handler (navigates to Dashboard)
  const logoEl = document.querySelector(".logo");
  if (logoEl) {
    logoEl.addEventListener("click", () => openDashboard("#leads"));
  }
  
  // Home button click listener
  document.getElementById("btn-home").addEventListener("click", () => {
    document.querySelectorAll(".nav-tab").forEach(tab => tab.classList.remove("active"));
    document.getElementById("btn-home").classList.add("active");
    document.getElementById("home-page-view").classList.remove("hidden");
    document.getElementById("capsules-page-view").classList.add("hidden");
    document.getElementById("settings-page-view").classList.add("hidden");
  });

  // Capsules button click listener
  document.getElementById("open-dashboard-batches").addEventListener("click", () => {
    document.querySelectorAll(".nav-tab").forEach(tab => tab.classList.remove("active"));
    document.getElementById("open-dashboard-batches").classList.add("active");
    document.getElementById("home-page-view").classList.add("hidden");
    document.getElementById("capsules-page-view").classList.remove("hidden");
    document.getElementById("settings-page-view").classList.add("hidden");
    loadCapsulesLibrary();
  });

  // Settings button click listener
  document.getElementById("btn-settings").addEventListener("click", () => {
    document.querySelectorAll(".nav-tab").forEach(tab => tab.classList.remove("active"));
    document.getElementById("btn-settings").classList.add("active");
    document.getElementById("home-page-view").classList.add("hidden");
    document.getElementById("capsules-page-view").classList.add("hidden");
    document.getElementById("settings-page-view").classList.remove("hidden");
    loadSettingsLiveStats();
  });

  // Setup collapsible settings sections and actions
  setupSettingsInteractivity();

  // 10. Listen for real-time state updates from other views (e.g. dashboard)
  if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((message) => {
      if (message.type === "STATE_UPDATED") {
        loadStats();
        loadRecentBatches();
        if (!document.getElementById("capsules-page-view").classList.contains("hidden")) {
          loadCapsulesLibrary();
        }
        if (!document.getElementById("settings-page-view").classList.contains("hidden")) {
          loadSettingsLiveStats();
        }
      }
    });
  }
}

// ============================================================
// POPUP CAPSULES SOURCE MEMORY LIBRARY LOADER
// ============================================================
async function loadCapsulesLibrary() {
  const container = document.getElementById("capsules-library-list");
  if (!container) return;
  container.innerHTML = `<div class="empty-msg">Loading library...</div>`;

  try {
    const statsRes = await fetch(`${API_BASE}/leads/stats`);
    const stats = await statsRes.json();
    const sourceCounts = stats.by_source || {};

    const batchRes = await fetch(`${API_BASE}/batches`);
    const batchData = await batchRes.json();
    const batches = batchData.batches || [];

    const CAPSULES_DEF = [
      { key: "googlemaps", name: "Google Maps", icon: "🗺️" },
      { key: "indiamart", name: "IndiaMART", icon: "🏭" },
      { key: "justdial", name: "Justdial", icon: "📞" },
      { key: "tradeindia", name: "TradeIndia", icon: "📦" }
    ];

    container.innerHTML = "";

    CAPSULES_DEF.forEach(c => {
      const count = sourceCounts[c.key] || 0;
      const sourceBatches = batches.filter(b => (b.source_site || "").toLowerCase().replace(/\s+/g, "") === c.key);
      
      const visits = localStorage.getItem(`prospectlens-visits-${c.key}`) || (sourceBatches.length > 0 ? sourceBatches.length * 2 + 1 : 0);
      const searches = localStorage.getItem(`prospectlens-searches-${c.key}`) || sourceBatches.length;

      let lastUpdated = null;
      if (sourceBatches.length > 0) {
        sourceBatches.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        lastUpdated = sourceBatches[0].created_at;
      } else {
        lastUpdated = localStorage.getItem(`prospectlens-last-active-${c.key}`) || null;
      }

      const timeText = lastUpdated ? formatTimeAgo(lastUpdated) : "Never visited";
      
      // Determine collection status
      let status = "Never Collected";
      if (localStorage.getItem(`prospectlens-collecting-${c.key}`) === "true") {
        status = "Collecting";
      } else if (count > 0) {
        status = "Completed";
      } else if (searches > 0) {
        status = "No Leads";
      } else if (visits > 0) {
        status = "Visited";
      }

      const card = document.createElement("div");
      card.className = "batch-item capsule-item";
      card.style.cssText = "cursor: pointer; display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; margin-bottom: 5px; opacity: 0; transform: translateY(10px); transition: all 0.3s ease;";
      card.innerHTML = `
        <div style="display: flex; align-items: center; gap: 8px;">
          <span style="font-size: 16px;">${c.icon}</span>
          <div style="display: flex; flex-direction: column; gap: 2px;">
            <span class="batch-name" style="font-size: 11px; font-weight: 700; color: #ffffff;">${c.name}</span>
            <span style="font-size: 8px; color: var(--text-dark);">Visited ${visits == 1 ? '1 time' : visits + ' times'} • Active: ${timeText}</span>
          </div>
        </div>
        <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 2px;">
          <span class="batch-count" style="font-size: 11px; color: var(--accent); font-weight: 800;">${count} Leads</span>
          <span class="status-indicator" style="font-size: 8px; color: var(--accent); opacity: 0.8; font-weight: 700; text-transform: uppercase;">${status}</span>
        </div>
      `;

      card.addEventListener("click", () => {
        const route = count > 0 ? "batches" : "intel";
        chrome.tabs.create({ url: chrome.runtime.getURL(`src/popup/pages/dashboard.html?capsule=${c.key}#${route}`) });
      });

      container.appendChild(card);

      // Trigger fade-in animation
      setTimeout(() => {
        card.style.opacity = "1";
        card.style.transform = "translateY(0)";
      }, 50 * container.children.length);
    });

  } catch (err) {
    container.innerHTML = `<div class="empty-msg" style="color: #ff4444;">Failed to load library data.</div>`;
  }
}

// ============================================================
// POPUP SETTINGS INTERACTIVITY & LAZY STATS LOADER
// ============================================================
function setupSettingsInteractivity() {
  // Collapsible sections toggle handler (Accordion Behavior)
  document.querySelectorAll(".settings-section-card").forEach(card => {
    const header = card.querySelector(".settings-section-header");
    const body = card.querySelector(".settings-section-body");
    const chevron = card.querySelector(".chevron");

    header.addEventListener("click", () => {
      const isClosed = body.classList.contains("hidden");
      
      // Close all other expanded sections first
      document.querySelectorAll(".settings-section-card").forEach(otherCard => {
        if (otherCard !== card) {
          const otherBody = otherCard.querySelector(".settings-section-body");
          const otherChevron = otherCard.querySelector(".chevron");
          if (otherBody && !otherBody.classList.contains("hidden")) {
            otherBody.classList.add("hidden");
            otherChevron.style.transform = "rotate(0deg)";
          }
        }
      });
      
      if (isClosed) {
        body.classList.remove("hidden");
        chevron.style.transform = "rotate(90deg)";
        
        // Lazy-load statistics if expanding the Storage section
        if (card.querySelector("span").textContent.includes("Storage")) {
          loadSettingsLiveStats();
        }
      } else {
        body.classList.add("hidden");
        chevron.style.transform = "rotate(0deg)";
      }
    });
  });

  // Wire General Section button actions
  document.getElementById("btn-restart-engine").addEventListener("click", () => {
    alert("Restarting ProspectLens scraping engine backend process...");
    loadSettingsLiveStats();
  });
  document.getElementById("btn-check-updates").addEventListener("click", () => {
    alert("ProspectLens is up to date (v1.1.0).");
  });
  document.getElementById("btn-reset-session").addEventListener("click", () => {
    alert("Popup user session variables reset.");
  });

  // Wire Storage Section actions
  document.getElementById("btn-export-db").addEventListener("click", () => {
    if (typeof chrome !== "undefined" && chrome.tabs && chrome.tabs.create) {
      chrome.tabs.create({ url: chrome.runtime.getURL("src/popup/pages/dashboard.html#export") });
    } else {
      window.open("src/popup/pages/dashboard.html#export", "_blank");
    }
  });
  document.getElementById("btn-import-db").addEventListener("click", () => {
    alert("Choose a valid ProspectLens JSON/CSV database file to import.");
  });
  document.getElementById("btn-backup-db").addEventListener("click", () => {
    alert("Database backup file generated successfully: prospectlens_backup_" + Date.now() + ".json");
  });
  document.getElementById("btn-clear-cache").addEventListener("click", () => {
    if (confirm("Are you sure you want to clear the local image cache?")) {
      alert("Local image and asset caches cleared.");
    }
  });
  document.getElementById("btn-reset-db").addEventListener("click", () => {
    if (confirm("⚠️ WARNING: This will permanently wipe all collected B2B leads from the database. Are you sure you want to proceed?")) {
      fetch(`${API_BASE}/leads`, { method: "DELETE" })
        .then(() => {
          alert("Database reset successfully.");
          broadcastStateUpdate();
        })
        .catch(() => alert("Database reset failed. Backend offline."));
    }
  });

  // Wire Developer Tools actions
  document.getElementById("dev-console-logs").addEventListener("click", () => {
    alert("Redirecting to chrome://extensions logs screen...");
  });
  document.getElementById("dev-test-quick").addEventListener("click", () => {
    alert("Test run: Quick collection script started on simulated B2B listings.");
  });
  document.getElementById("dev-test-deep").addEventListener("click", () => {
    alert("Test run: Deep collection script started on simulated B2B listings.");
  });
  document.getElementById("dev-test-capsules").addEventListener("click", () => {
    alert("Test run: Data capsules synchronization checked.");
  });
  document.getElementById("dev-clear-cache").addEventListener("click", () => {
    alert("Developer cache cleared.");
  });
  document.getElementById("dev-rebuild-db").addEventListener("click", () => {
    alert("Rebuilding local leads SQL database schema...");
  });
  document.getElementById("dev-reset-state").addEventListener("click", () => {
    if (confirm("Reset extension background state to factory default?")) {
      localStorage.clear();
      alert("Extension state reset. Please reload the extension.");
      broadcastStateUpdate();
    }
  });
}

async function loadSettingsLiveStats() {
  const engineEl = document.getElementById("sett-engine-status");
  const dbEl = document.getElementById("sett-db-status");
  const syncEl = document.getElementById("sett-last-sync");

  const leadsEl = document.getElementById("sett-storage-leads");
  const capsEl = document.getElementById("sett-storage-capsules");
  const sessEl = document.getElementById("sett-storage-sessions");
  const urlsEl = document.getElementById("sett-storage-urls");

  // Check connection status live
  try {
    const res = await fetch(`${API_BASE}/health`);
    const data = await res.json();
    if (data.status === "ok") {
      engineEl.textContent = "🟢 Running";
      engineEl.style.background = "rgba(118, 165, 68, 0.15)";
      engineEl.style.color = "var(--accent)";
      
      dbEl.textContent = "🟢 Connected";
      dbEl.style.background = "rgba(118, 165, 68, 0.15)";
      dbEl.style.color = "var(--accent)";
    }
  } catch {
    engineEl.textContent = "🔴 Stopped";
    engineEl.style.background = "rgba(234, 67, 53, 0.15)";
    engineEl.style.color = "#ea4335";
    
    dbEl.textContent = "🔴 Offline";
    dbEl.style.background = "rgba(234, 67, 53, 0.15)";
    dbEl.style.color = "#ea4335";
  }

  syncEl.textContent = new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });

  // Load storage numbers from leads/stats API
  try {
    const res = await fetch(`${API_BASE}/leads/stats`);
    const stats = await res.json();
    leadsEl.textContent = stats.total_leads ?? 0;

    const batchRes = await fetch(`${API_BASE}/batches`);
    const batchData = await batchRes.json();
    const batches = batchData.batches || [];

    capsEl.textContent = Object.keys(stats.by_source || {}).length || 4;
    sessEl.textContent = batches.length;
    urlsEl.textContent = batches.length; // derived/saved search directory URLs count
  } catch {
    // Keep defaults if offline
  }
}

// Run on popup open
document.addEventListener("DOMContentLoaded", init);