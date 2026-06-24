/**
 * Enterprise Zero-Failure Error Boundary
 * =======================================
 * Never lets a JavaScript error crash the application.
 * Provides user-friendly fallbacks, logging, and recovery.
 * 
 * - Global error handler (window.onerror)
 * - Unhandled promise rejection handler
 * - Safe DOM access utilities
 * - Safe JSON parse
 * - Toast error notification system (duplicate-safe)
 * - Null/undefined guard helpers
 */

(function () {
  'use strict';

  // ── Logging ────────────────────────────────────────────────────────────────
  const LOG_PREFIX = '[ErrorBoundary]';
  const MAX_LOG_ENTRIES = 200;
  const errorLog = [];

  function logError(severity, context, error) {
    const entry = {
      timestamp: new Date().toISOString(),
      severity,
      context,
      message: error ? (error.message || String(error)) : 'Unknown error',
      stack: error ? (error.stack || '') : ''
    };
    errorLog.push(entry);
    if (errorLog.length > MAX_LOG_ENTRIES) errorLog.shift();
    console.warn(LOG_PREFIX, severity, context, error || '');
  }

  // ── Global Error Handler ──────────────────────────────────────────────────
  window.onerror = function (message, source, lineno, colno, error) {
    logError('CRITICAL', 'window.onerror', error || message);
    // Never let the error bubble to break the page
    showFallbackToast('An unexpected error occurred. The application has recovered.', 'error');
    return true; // Prevents default browser error handling
  };

  // ── Unhandled Promise Rejection Handler ───────────────────────────────────
  window.addEventListener('unhandledrejection', function (event) {
    logError('CRITICAL', 'unhandledrejection', event.reason);
    event.preventDefault();
    showFallbackToast('A background operation failed. Continuing safely.', 'error');
  });

  // ── Safe DOM Access ──────────────────────────────────────────────────────
  window.__safe = {};

  /**
   * Safely get an element by ID. Returns null if not found (no exception).
   * @param {string} id
   * @returns {HTMLElement|null}
   */
  __safe.getElementById = function (id) {
    try {
      return document.getElementById(id);
    } catch (e) {
      logError('WARN', 'getElementById("' + id + '")', e);
      return null;
    }
  };

  /**
   * Safely querySelector. Returns null on failure.
   * @param {string} selector
   * @param {HTMLElement} [context=document]
   * @returns {HTMLElement|null}
   */
  __safe.querySelector = function (selector, context) {
    try {
      return (context || document).querySelector(selector);
    } catch (e) {
      logError('WARN', 'querySelector("' + selector + '")', e);
      return null;
    }
  };

  /**
   * Safely querySelectorAll. Returns empty array on failure.
   * @param {string} selector
   * @param {HTMLElement} [context=document]
   * @returns {HTMLElement[]}
   */
  __safe.querySelectorAll = function (selector, context) {
    try {
      return Array.from((context || document).querySelectorAll(selector));
    } catch (e) {
      logError('WARN', 'querySelectorAll("' + selector + '")', e);
      return [];
    }
  };

  /**
   * Safely set innerHTML on an element.
   * @param {HTMLElement|null} el
   * @param {string} html
   * @returns {boolean} true if successful
   */
  __safe.setInnerHTML = function (el, html) {
    if (!el) return false;
    try {
      el.innerHTML = html;
      return true;
    } catch (e) {
      logError('WARN', 'setInnerHTML', e);
      return false;
    }
  };

  /**
   * Safely set textContent on an element.
   * @param {HTMLElement|null} el
   * @param {string} text
   * @returns {boolean}
   */
  __safe.setTextContent = function (el, text) {
    if (!el) return false;
    try {
      el.textContent = String(text || '');
      return true;
    } catch (e) {
      return false;
    }
  };

  /**
   * Safely add an event listener.
   * @param {HTMLElement|null} el
   * @param {string} event
   * @param {Function} handler
   * @returns {boolean}
   */
  __safe.addListener = function (el, event, handler) {
    if (!el || typeof handler !== 'function') return false;
    try {
      el.addEventListener(event, handler);
      return true;
    } catch (e) {
      logError('WARN', 'addListener("' + event + '")', e);
      return false;
    }
  };

  // ── Safe JSON Operations ──────────────────────────────────────────────────
  
  /**
   * Safely parse JSON. Returns fallback on failure.
   * @param {string} text
   * @param {*} fallback
   * @returns {*}
   */
  __safe.parseJSON = function (text, fallback) {
    if (text === null || text === undefined || text === '') return fallback;
    try {
      return JSON.parse(text);
    } catch (e) {
      logError('WARN', 'parseJSON', e);
      return arguments.length >= 2 ? fallback : null;
    }
  };

  /**
   * Safely stringify to JSON. Returns fallback on failure.
   * @param {*} value
   * @param {*} fallback
   * @returns {string}
   */
  __safe.stringifyJSON = function (value, fallback) {
    try {
      return JSON.stringify(value);
    } catch (e) {
      logError('WARN', 'stringifyJSON', e);
      return arguments.length >= 2 ? fallback : '';
    }
  };

  // ── Safe Property Access ──────────────────────────────────────────────────
  
  /**
   * Safely get a nested property from an object. Returns default on failure.
   * @param {*} obj
   * @param {...string} keys
   * @returns {*}
   */
  __safe.get = function (obj) {
    if (obj === null || obj === undefined) return undefined;
    var current = obj;
    var keys = Array.prototype.slice.call(arguments, 1);
    for (var i = 0; i < keys.length; i++) {
      if (current === null || current === undefined) return undefined;
      try {
        current = current[keys[i]];
      } catch (e) {
        return undefined;
      }
    }
    return current;
  };

  /**
   * Safely get a nested property with a default value.
   * @param {*} obj
   * @param {*} defaultVal
   * @param {...string} keys
   * @returns {*}
   */
  __safe.getOrDefault = function (obj, defaultVal) {
    var keys = Array.prototype.slice.call(arguments, 2);
    var val = __safe.get.apply(null, [obj].concat(keys));
    return val !== undefined ? val : defaultVal;
  };

  // ── Number Safety ─────────────────────────────────────────────────────────
  
  /**
   * Safely convert a value to a number. Returns fallback on failure.
   * @param {*} v
   * @param {number} [fallback=0]
   * @returns {number}
   */
  __safe.toNumber = function (v, fallback) {
    if (v === null || v === undefined) return fallback !== undefined ? fallback : 0;
    if (typeof fallback === 'undefined') fallback = 0;
    var n = Number(v);
    return isNaN(n) ? fallback : n;
  };

  /**
   * Safely format a number as locale string.
   * @param {*} v
   * @param {string} [fallback='0']
   * @returns {string}
   */
  __safe.formatNumber = function (v, fallback) {
    if (fallback === undefined) fallback = '0';
    try {
      var n = __safe.toNumber(v);
      return n.toLocaleString();
    } catch (e) {
      return fallback;
    }
  };

  // ── Array Safety ──────────────────────────────────────────────────────────
  
  /**
   * Safely get array length.
   * @param {*} arr
   * @returns {number}
   */
  __safe.len = function (arr) {
    if (arr === null || arr === undefined) return 0;
    if (Array.isArray(arr)) return arr.length;
    return 0;
  };

  /**
   * Safely get an array element by index.
   * @param {*} arr
   * @param {number} index
   * @param {*} [fallback]
   * @returns {*}
   */
  __safe.at = function (arr, index, fallback) {
    if (!Array.isArray(arr)) return fallback;
    if (index < 0 || index >= arr.length) return fallback;
    return arr[index];
  };



  // ── Toast System (fallback-safe) ──────────────────────────────────────────
  var toastQueue = [];
  var TOAST_LIMIT = 5;

  function showFallbackToast(message, type) {
    type = type || 'error';
    try {
      // Check if existing toast container exists
      var container = document.getElementById('toastContainer');
      if (!container) {
        // Create fallback toast container
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container';
        container.style.cssText = 'position:fixed;top:16px;right:16px;z-index:10000;display:flex;flex-direction:column;gap:8px;max-width:400px;';
        var body = document.body;
        if (body) body.appendChild(container);
      }
      
      // Limit toasts
      if (toastQueue.length >= TOAST_LIMIT) {
        var oldest = toastQueue.shift();
        if (oldest && oldest.parentNode) oldest.parentNode.removeChild(oldest);
      }
      
      var toast = document.createElement('div');
      toast.className = 'toast toast-' + type;
      toast.style.cssText = 'display:flex;align-items:center;gap:8px;padding:12px 16px;border-radius:8px;background:#1a1a2e;color:#fff;box-shadow:0 4px 12px rgba(0,0,0,0.15);animation:slideIn 0.3s ease;font-size:13px;line-height:1.4;min-width:200px;';
      
      var iconMap = {
        success: '\u2705',
        error: '\u274C',
        info: '\u2139\uFE0F',
        warning: '\u26A0\uFE0F'
      };
      toast.innerHTML = '<span style="flex-shrink:0;font-size:16px;">' + (iconMap[type] || iconMap.info) + '</span>' +
        '<span style="flex:1;">' + String(message) + '</span>' +
        '<button onclick="this.parentNode.remove()" style="flex-shrink:0;background:none;border:none;color:#999;cursor:pointer;font-size:16px;padding:0 4px;">\u00D7</button>';
      
      container.appendChild(toast);
      toastQueue.push(toast);
      
      // Auto-dismiss after 5 seconds
      setTimeout(function () {
        if (toast && toast.parentNode) {
          toast.style.opacity = '0';
          toast.style.transform = 'translateX(100%)';
          toast.style.transition = 'all 0.3s ease';
          setTimeout(function () {
            if (toast && toast.parentNode) {
              toast.parentNode.removeChild(toast);
            }
          }, 300);
        }
        var idx = toastQueue.indexOf(toast);
        if (idx >= 0) toastQueue.splice(idx, 1);
      }, 5000);
    } catch (e) {
      // Last resort - console only
      console.error('[ErrorBoundary] Fallback toast failed:', message, e);
    }
  }

  window.__safe.showToast = showFallbackToast;

  // ── DOM Ready Helper ──────────────────────────────────────────────────────
  
  __safe.onReady = function (fn) {
    if (typeof fn !== 'function') return;
    try {
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', fn);
      } else {
        fn();
      }
    } catch (e) {
      logError('WARN', 'onReady', e);
    }
  };

  // ── Expose error log for debugging ────────────────────────────────────────
  window.__safe.getErrorLog = function () {
    return errorLog.slice();
  };

  console.log('[ErrorBoundary] Enterprise zero-failure protection active.');
})();