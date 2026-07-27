// src/content-scripts/engine/stateManager.js
// ProspectLens — Collection state manager

const StateManager = {
  states: {
    IDLE: "Idle",
    RUNNING: "Running",
    PAUSED: "Paused",
    STOPPED: "Stopped",
    STOPPING: "Stopping",
    COMPLETED: "Completed",
    OFFLINE: "Offline"
  },
  currentState: "Idle",
  
  setState(newState) {
    this.currentState = newState;
    Logger.log(`StateManager: State changed to ${newState}`);
  },
  
  getState() {
    return this.currentState;
  }
};
window.StateManager = StateManager;
