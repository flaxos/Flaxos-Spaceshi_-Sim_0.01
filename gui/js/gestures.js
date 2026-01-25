/**
 * Gesture Handler
 * Phase 6: Mobile Optimization
 * 
 * Handles touch gestures for mobile UI:
 * - Swipe left/right: change tabs
 * - Long press: context menu (future)
 * - Double-tap: quick action
 */

class GestureHandler {
  constructor() {
    this._touchStartX = 0;
    this._touchStartY = 0;
    this._touchStartTime = 0;
    this._lastTapTime = 0;
    this._longPressTimer = null;
    this._isLongPress = false;

    // Configuration
    this.config = {
      swipeThreshold: 50,        // Minimum distance for swipe (px)
      swipeMaxTime: 500,         // Maximum time for swipe (ms)
      swipeDirectionRatio: 1.5,  // Horizontal vs vertical ratio
      doubleTapThreshold: 300,   // Max time between taps (ms)
      longPressThreshold: 500,   // Time to trigger long press (ms)
    };

    // Registered callbacks
    this._callbacks = {
      swipeLeft: [],
      swipeRight: [],
      swipeUp: [],
      swipeDown: [],
      doubleTap: [],
      longPress: [],
    };
  }

  /**
   * Initialize gesture handling on an element
   * @param {HTMLElement} element - Element to attach gestures to
   * @param {Object} options - Override default config
   */
  attach(element, options = {}) {
    this.config = { ...this.config, ...options };

    element.addEventListener("touchstart", (e) => this._handleTouchStart(e), { passive: true });
    element.addEventListener("touchmove", (e) => this._handleTouchMove(e), { passive: false });
    element.addEventListener("touchend", (e) => this._handleTouchEnd(e), { passive: true });
    element.addEventListener("touchcancel", (e) => this._handleTouchCancel(e), { passive: true });

    return this;
  }

  /**
   * Register a callback for a gesture
   * @param {string} gesture - Gesture name
   * @param {Function} callback - Callback function
   */
  on(gesture, callback) {
    if (this._callbacks[gesture]) {
      this._callbacks[gesture].push(callback);
    }
    return this;
  }

  /**
   * Remove a callback
   * @param {string} gesture - Gesture name
   * @param {Function} callback - Callback to remove
   */
  off(gesture, callback) {
    if (this._callbacks[gesture]) {
      const idx = this._callbacks[gesture].indexOf(callback);
      if (idx !== -1) {
        this._callbacks[gesture].splice(idx, 1);
      }
    }
    return this;
  }

  /**
   * Emit a gesture event
   */
  _emit(gesture, data = {}) {
    this._callbacks[gesture]?.forEach(cb => {
      try {
        cb(data);
      } catch (e) {
        console.error(`Gesture callback error (${gesture}):`, e);
      }
    });
  }

  _handleTouchStart(e) {
    if (e.touches.length !== 1) return;

    const touch = e.touches[0];
    this._touchStartX = touch.clientX;
    this._touchStartY = touch.clientY;
    this._touchStartTime = Date.now();
    this._isLongPress = false;

    // Start long press timer
    this._longPressTimer = setTimeout(() => {
      this._isLongPress = true;
      this._emit("longPress", {
        x: this._touchStartX,
        y: this._touchStartY,
      });
    }, this.config.longPressThreshold);
  }

  _handleTouchMove(e) {
    // Cancel long press on move
    if (this._longPressTimer) {
      clearTimeout(this._longPressTimer);
      this._longPressTimer = null;
    }

    // Check if we should prevent default (for horizontal swipes)
    if (e.touches.length === 1) {
      const touch = e.touches[0];
      const deltaX = Math.abs(touch.clientX - this._touchStartX);
      const deltaY = Math.abs(touch.clientY - this._touchStartY);

      // If horizontal swipe is dominant, prevent scroll
      if (deltaX > deltaY * this.config.swipeDirectionRatio && deltaX > 10) {
        e.preventDefault();
      }
    }
  }

  _handleTouchEnd(e) {
    // Cancel long press timer
    if (this._longPressTimer) {
      clearTimeout(this._longPressTimer);
      this._longPressTimer = null;
    }

    // Skip if this was a long press
    if (this._isLongPress) {
      this._isLongPress = false;
      return;
    }

    const touch = e.changedTouches[0];
    const deltaX = touch.clientX - this._touchStartX;
    const deltaY = touch.clientY - this._touchStartY;
    const deltaTime = Date.now() - this._touchStartTime;
    const absX = Math.abs(deltaX);
    const absY = Math.abs(deltaY);

    // Check for double tap
    if (absX < 10 && absY < 10 && deltaTime < 200) {
      const now = Date.now();
      if (now - this._lastTapTime < this.config.doubleTapThreshold) {
        this._emit("doubleTap", { x: touch.clientX, y: touch.clientY });
        this._lastTapTime = 0; // Reset
        return;
      }
      this._lastTapTime = now;
    }

    // Check for swipe
    if (deltaTime > this.config.swipeMaxTime) return;
    if (absX < this.config.swipeThreshold && absY < this.config.swipeThreshold) return;

    // Determine swipe direction
    if (absX > absY * this.config.swipeDirectionRatio) {
      // Horizontal swipe
      if (deltaX > 0) {
        this._emit("swipeRight", { deltaX, deltaY, deltaTime });
      } else {
        this._emit("swipeLeft", { deltaX, deltaY, deltaTime });
      }
    } else if (absY > absX * this.config.swipeDirectionRatio) {
      // Vertical swipe
      if (deltaY > 0) {
        this._emit("swipeDown", { deltaX, deltaY, deltaTime });
      } else {
        this._emit("swipeUp", { deltaX, deltaY, deltaTime });
      }
    }
  }

  _handleTouchCancel(e) {
    if (this._longPressTimer) {
      clearTimeout(this._longPressTimer);
      this._longPressTimer = null;
    }
    this._isLongPress = false;
  }
}

/**
 * Create a gesture handler for the mobile layout
 */
function initMobileGestures() {
  const grid = document.getElementById("interface-grid");
  if (!grid) return null;

  const handler = new GestureHandler();
  handler.attach(grid);

  // Wire up tab switching on swipe
  handler.on("swipeLeft", () => {
    const mobileLayout = window.flaxosApp?.mobileLayout;
    if (mobileLayout?.isActive()) {
      const tabs = ["nav", "sen", "wpn", "log", "sys"];
      const currentIdx = tabs.indexOf(mobileLayout.getCurrentTab());
      if (currentIdx < tabs.length - 1) {
        mobileLayout.switchTab(tabs[currentIdx + 1]);
      }
    }
  });

  handler.on("swipeRight", () => {
    const mobileLayout = window.flaxosApp?.mobileLayout;
    if (mobileLayout?.isActive()) {
      const tabs = ["nav", "sen", "wpn", "log", "sys"];
      const currentIdx = tabs.indexOf(mobileLayout.getCurrentTab());
      if (currentIdx > 0) {
        mobileLayout.switchTab(tabs[currentIdx - 1]);
      }
    }
  });

  return handler;
}

// Export
export { GestureHandler, initMobileGestures };
