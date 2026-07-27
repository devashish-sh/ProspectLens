// src/background/engine_manager.js
// ProspectLens — Dedicated Backend Engine Lifecycle Manager
//
// Manages startup, shutdown, health monitoring, logging, and configuration of the Uvicorn backend process.

const API_BASE = "http://localhost:8000/api";
const HOST_NAME = "com.prospectlens.launcher";
const DEFAULT_LAUNCHER_PATH = "C:\\Users\\devas\\Desktop\\ProspectLens\\start.bat";

export class EngineManager {
  static async init() {
    console.log("[Engine] Initializing EngineManager...");
    
    // Load config or set defaults
    const config = await chrome.storage.local.get([
      "engineState",
      "launcherPath",
      "lastStartupTime",
      "lastShutdownTime"
    ]);

    if (!config.launcherPath) {
      await chrome.storage.local.set({ launcherPath: DEFAULT_LAUNCHER_PATH });
    }
    
    // Always reset to OFFLINE or check status on service worker load
    const isOnline = await this.checkHealth();
    const initialState = isOnline ? "RUNNING" : "OFFLINE";
    await this.updateState(initialState);

    // Start continuous health monitoring
    this.startHealthMonitor();
  }

  static async getLauncherPath() {
    const data = await chrome.storage.local.get("launcherPath");
    return data.launcherPath || DEFAULT_LAUNCHER_PATH;
  }

  static async setLauncherPath(path) {
    await chrome.storage.local.set({ launcherPath: path });
    console.log(`[Engine] Launcher path updated to: ${path}`);
  }

  static async restoreDefaultLauncherPath() {
    await chrome.storage.local.set({ launcherPath: DEFAULT_LAUNCHER_PATH });
    console.log(`[Engine] Restored default launcher path: ${DEFAULT_LAUNCHER_PATH}`);
  }

  static async updateState(newState) {
    const data = { engineState: newState };
    
    if (newState === "RUNNING") {
      data.lastStartupTime = new Date().toLocaleTimeString("en-IN", { hour12: true });
    } else if (newState === "OFFLINE") {
      const current = await chrome.storage.local.get("engineState");
      if (current.engineState === "STOPPING") {
        data.lastShutdownTime = new Date().toLocaleTimeString("en-IN", { hour12: true });
      }
    }
    
    await chrome.storage.local.set(data);
    console.log(`[Engine] State changed: ${newState}`);
  }

  static async checkHealth() {
    try {
      const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(1500) });
      const data = await res.json();
      return data.status === "ok";
    } catch {
      return false;
    }
  }

  static async startEngine() {
    const launcherPath = await this.getLauncherPath();
    console.log(`[Engine] Starting backend... (Launcher: ${launcherPath})`);
    await this.updateState("STARTING");

    return new Promise((resolve) => {
      // 1. Send native message to launch start.bat
      chrome.runtime.sendNativeMessage(
        HOST_NAME,
        { action: "start", launcher_path: launcherPath },
        async (response) => {
          if (chrome.runtime.lastError) {
            console.error("[Engine] Native host error:", chrome.runtime.lastError.message);
            await this.updateState("OFFLINE");
            resolve({ success: false, error: "Backend launcher not found or failed to execute." });
            return;
          }

          if (response && response.status === "error") {
            console.error("[Engine] Launcher failed:", response.message);
            await this.updateState("OFFLINE");
            resolve({ success: false, error: response.message });
            return;
          }

          console.log("[Engine] Backend launched. Waiting for health...");

          // 2. Poll health endpoint until success or timeout (30 seconds)
          let attempts = 0;
          const maxAttempts = 30;
          const pollInterval = setInterval(async () => {
            attempts++;
            const isHealthy = await this.checkHealth();
            
            if (isHealthy) {
              clearInterval(pollInterval);
              console.log("[Engine] Health OK. Engine Running.");
              await this.updateState("RUNNING");
              resolve({ success: true });
            } else if (attempts >= maxAttempts) {
              clearInterval(pollInterval);
              console.error("[Engine] Startup timed out waiting for backend health.");
              await this.updateState("OFFLINE");
              resolve({ success: false, error: "Unable to start backend. Startup timed out." });
            }
          }, 1000);
        }
      );
    });
  }

  static async stopEngine() {
    console.log("[Engine] Stopping backend...");
    await this.updateState("STOPPING");

    return new Promise((resolve) => {
      chrome.runtime.sendNativeMessage(
        HOST_NAME,
        { action: "stop" },
        async (response) => {
          if (chrome.runtime.lastError) {
            console.warn("[Engine] Native stop warning:", chrome.runtime.lastError.message);
          }

          // Poll health until offline
          let attempts = 0;
          const maxAttempts = 10;
          const pollInterval = setInterval(async () => {
            attempts++;
            const isHealthy = await this.checkHealth();
            if (!isHealthy) {
              clearInterval(pollInterval);
              console.log("[Engine] Backend stopped. Engine Offline.");
              await this.updateState("OFFLINE");
              resolve({ success: true });
            } else if (attempts >= maxAttempts) {
              clearInterval(pollInterval);
              console.error("[Engine] Shutdown verification timed out.");
              // Force offline state anyway
              await this.updateState("OFFLINE");
              resolve({ success: true });
            }
          }, 1000);
        }
      );
    });
  }

  static startHealthMonitor() {
    // Check health every 5 seconds
    setInterval(async () => {
      const store = await chrome.storage.local.get("engineState");
      const currentState = store.engineState || "OFFLINE";
      
      if (currentState === "RUNNING") {
        const isHealthy = await this.checkHealth();
        if (!isHealthy) {
          console.warn("[Engine] Connection lost. Backend crashed or exited.");
          await this.updateState("OFFLINE");
          
          // Trigger browser notification
          chrome.notifications.create({
            type: "basic",
            iconUrl: "/icons/icon128.png",
            title: "ProspectLens Alert",
            message: "The ProspectLens background engine stopped unexpectedly.",
            priority: 2
          });
        }
      } else if (currentState === "OFFLINE") {
        const isHealthy = await this.checkHealth();
        if (isHealthy) {
          console.log("[Engine] Connection restored. Setting state to RUNNING.");
          await this.updateState("RUNNING");
        }
      }
    }, 5000);
  }
}
