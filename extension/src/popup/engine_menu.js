// engine_menu.js — ProspectLens System Health Dropdown Control Logic
// Listens to status badge class mutations to update diagnostic stats and handles heartbeat counting.

(function () {
  const statusBadge = document.getElementById("backend-status");
  const dropdown    = document.getElementById("status-dropdown");
  const arrowEl     = statusBadge?.querySelector(".status-arrow");

  if (!statusBadge || !dropdown) return;

  // ============================================================
  // DROPDOWN MENU TOGGLE
  // ============================================================
  statusBadge.addEventListener("click", (e) => {
    e.stopPropagation();
    const isShowing = dropdown.classList.toggle("show");
    
    if (arrowEl) {
      arrowEl.style.transform = isShowing ? "rotate(180deg)" : "rotate(0deg)";
      arrowEl.style.transition = "transform 0.2s ease";
    }

  });

  // Close dropdown on click outside
  window.addEventListener("click", (e) => {
    if (!e.target.closest(".status-wrapper") && !e.target.closest(".popup-overlay")) {
      dropdown.classList.remove("show");
      if (arrowEl) {
        arrowEl.style.transform = "rotate(0deg)";
      }
    }
  });

  // ============================================================
  // PING & HEARTBEAT TIMER
  // ============================================================
  let heartbeatSeconds = 0;
  const heartbeatVal   = document.getElementById("health-heartbeat");

  // Increment heartbeat counter every second
  setInterval(() => {
    heartbeatSeconds++;
    if (heartbeatVal) {
      if (heartbeatSeconds <= 2) {
        heartbeatVal.textContent = "Just now";
      } else {
        heartbeatVal.textContent = `${heartbeatSeconds} seconds ago`;
      }
    }
  }, 1000);

  function resetHeartbeat() {
    heartbeatSeconds = 0;
    if (heartbeatVal) {
      heartbeatVal.textContent = "Just now";
    }
  }

  // ============================================================
  // DYNAMIC DIAGNOSTIC STATS SYNCING
  // ============================================================
  const dotBackend = document.getElementById("health-dot-backend");
  const valBackend = document.getElementById("health-val-backend");

  const dotApi = document.getElementById("health-dot-api");
  const valApi = document.getElementById("health-val-api");

  const dotDb = document.getElementById("health-dot-db");
  const valDb = document.getElementById("health-val-db");

  function setElementState(dotEl, valEl, state) {
    if (!dotEl || !valEl) return;
    
    // Clear old classes
    dotEl.className = "health-dot";
    valEl.className = "health-status";

    if (state === "online") {
      dotEl.classList.add("dot-green");
      valEl.classList.add("status-green");
      if (dotEl === dotBackend) valEl.textContent = "Running";
      if (dotEl === dotApi) valEl.textContent = "Connected";
      if (dotEl === dotDb) valEl.textContent = "Healthy";
    } else if (state === "offline") {
      dotEl.classList.add("dot-red");
      valEl.classList.add("status-red");
      if (dotEl === dotBackend) valEl.textContent = "Stopped";
      if (dotEl === dotApi) valEl.textContent = "Disconnected";
      if (dotEl === dotDb) valEl.textContent = "Unreachable";
    } else if (state === "checking") {
      dotEl.classList.add("dot-yellow");
      valEl.classList.add("status-yellow");
      valEl.textContent = "Checking...";
    }
  }

  // Sync function that checks the class on #backend-status and updates dropdown
  function syncSystemHealth() {
    const isOnline   = statusBadge.classList.contains("status-online");
    const isOffline  = statusBadge.classList.contains("status-offline");
    const isChecking = statusBadge.classList.contains("status-checking");

    if (isOnline) {
      setElementState(dotBackend, valBackend, "online");
      setElementState(dotApi, valApi, "online");
      setElementState(dotDb, valDb, "online");
      resetHeartbeat();
    } else if (isOffline) {
      setElementState(dotBackend, valBackend, "offline");
      setElementState(dotApi, valApi, "offline");
      setElementState(dotDb, valDb, "offline");
    } else if (isChecking) {
      setElementState(dotBackend, valBackend, "checking");
      setElementState(dotApi, valApi, "checking");
      setElementState(dotDb, valDb, "checking");
    }
    
  }

  // Create a MutationObserver to watch class changes on the status badge
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.type === "attributes" && mutation.attributeName === "class") {
        syncSystemHealth();
      }
    });
  });

  observer.observe(statusBadge, { attributes: true });

  // Initial Sync
  syncSystemHealth();

})();
