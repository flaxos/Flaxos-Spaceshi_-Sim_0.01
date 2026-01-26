/**
 * Helm Requests Manager
 * Inter-station communication for bridge crew coordination
 *
 * Allows other stations (Tactical, Navigation, etc.) to send
 * maneuver requests to the Helm station for execution.
 */

class HelmRequestsManager extends EventTarget {
  constructor() {
    super();
    this._requests = [];
    this._nextId = 1;
  }

  /**
   * Create a new helm request
   * @param {Object} request - The request details
   * @param {string} request.type - Request type: 'point_at', 'intercept', 'match_velocity', etc.
   * @param {string} request.source - Source station: 'tactical', 'navigation', 'sensors', etc.
   * @param {Object} request.params - Parameters for the request
   * @param {string} [request.targetId] - Target contact ID if applicable
   * @param {string} [request.description] - Human-readable description
   * @returns {Object} The created request with ID and timestamp
   */
  createRequest(request) {
    const newRequest = {
      id: this._nextId++,
      type: request.type,
      source: request.source || 'unknown',
      params: request.params || {},
      targetId: request.targetId || null,
      description: request.description || this._generateDescription(request),
      timestamp: Date.now(),
      status: 'pending'
    };

    this._requests.push(newRequest);

    // Dispatch event for listeners
    this.dispatchEvent(new CustomEvent('request_created', {
      detail: newRequest
    }));

    // Also dispatch on window for cross-component communication
    window.dispatchEvent(new CustomEvent('helm:request_created', {
      detail: newRequest
    }));

    console.log('[HelmRequests] Created request:', newRequest);
    return newRequest;
  }

  /**
   * Generate a human-readable description for a request
   */
  _generateDescription(request) {
    switch (request.type) {
      case 'point_at':
        const p = request.params;
        return `Point at ${request.targetId || 'target'}: P: ${p.pitch?.toFixed(1)}° | Y: ${p.yaw?.toFixed(1)}°`;
      case 'intercept':
        return `Intercept ${request.targetId || 'target'}`;
      case 'match_velocity':
        return `Match velocity with ${request.targetId || 'target'}`;
      case 'set_heading':
        const h = request.params;
        return `Set heading: P: ${h.pitch?.toFixed(1)}° | Y: ${h.yaw?.toFixed(1)}°`;
      default:
        return `${request.type} request`;
    }
  }

  /**
   * Get all pending requests
   * @returns {Array} Array of pending requests
   */
  getPendingRequests() {
    return this._requests.filter(r => r.status === 'pending');
  }

  /**
   * Get all requests (including executed/dismissed)
   * @returns {Array} Array of all requests
   */
  getAllRequests() {
    return [...this._requests];
  }

  /**
   * Execute a request (mark as executed and optionally perform action)
   * @param {number} requestId - The request ID to execute
   * @param {boolean} [performAction=true] - Whether to actually send the command
   * @returns {Object|null} The executed request or null if not found
   */
  async executeRequest(requestId, performAction = true) {
    const request = this._requests.find(r => r.id === requestId);
    if (!request || request.status !== 'pending') {
      return null;
    }

    request.status = 'executed';
    request.executedAt = Date.now();

    // Dispatch event
    this.dispatchEvent(new CustomEvent('request_executed', {
      detail: request
    }));

    window.dispatchEvent(new CustomEvent('helm:request_executed', {
      detail: request
    }));

    console.log('[HelmRequests] Executed request:', request);
    return request;
  }

  /**
   * Dismiss a request (mark as dismissed without executing)
   * @param {number} requestId - The request ID to dismiss
   * @returns {Object|null} The dismissed request or null if not found
   */
  dismissRequest(requestId) {
    const request = this._requests.find(r => r.id === requestId);
    if (!request || request.status !== 'pending') {
      return null;
    }

    request.status = 'dismissed';
    request.dismissedAt = Date.now();

    // Dispatch event
    this.dispatchEvent(new CustomEvent('request_dismissed', {
      detail: request
    }));

    window.dispatchEvent(new CustomEvent('helm:request_dismissed', {
      detail: request
    }));

    console.log('[HelmRequests] Dismissed request:', request);
    return request;
  }

  /**
   * Clear old requests (keep recent ones for history)
   * @param {number} [maxAge=300000] - Maximum age in ms (default 5 minutes)
   */
  clearOldRequests(maxAge = 300000) {
    const cutoff = Date.now() - maxAge;
    this._requests = this._requests.filter(r =>
      r.status === 'pending' || r.timestamp > cutoff
    );
  }

  /**
   * Get request count by status
   * @returns {Object} Counts by status
   */
  getRequestCounts() {
    const counts = { pending: 0, executed: 0, dismissed: 0 };
    this._requests.forEach(r => {
      counts[r.status] = (counts[r.status] || 0) + 1;
    });
    return counts;
  }
}

// Utility: Calculate 3D bearing from one position to another
function calculate3DBearing(fromPos, toPos) {
  const dx = (toPos.x ?? toPos[0] ?? 0) - (fromPos.x ?? fromPos[0] ?? 0);
  const dy = (toPos.y ?? toPos[1] ?? 0) - (fromPos.y ?? fromPos[1] ?? 0);
  const dz = (toPos.z ?? toPos[2] ?? 0) - (fromPos.z ?? fromPos[2] ?? 0);

  // Calculate horizontal distance for pitch calculation
  const horizontalDistance = Math.sqrt(dx * dx + dy * dy);

  // Calculate range (3D distance)
  const range = Math.sqrt(dx * dx + dy * dy + dz * dz);

  // Calculate yaw (horizontal angle)
  // atan2(dy, dx) gives angle from +X axis
  let yaw = Math.atan2(dy, dx) * (180 / Math.PI);

  // Calculate pitch (vertical angle)
  // Positive pitch = target is above, negative = below
  let pitch = 0;
  if (horizontalDistance > 0.001 || Math.abs(dz) > 0.001) {
    pitch = Math.atan2(dz, horizontalDistance) * (180 / Math.PI);
  }

  return {
    pitch: pitch,
    yaw: yaw,
    range: range,
    // Also provide normalized yaw (0-360)
    yawNormalized: ((yaw % 360) + 360) % 360
  };
}

// Export singleton instance and utility
const helmRequests = new HelmRequestsManager();
export { HelmRequestsManager, helmRequests, calculate3DBearing };
