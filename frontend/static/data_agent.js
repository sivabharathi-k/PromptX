/* Dataset Data Agent — integrates dataset editing into the existing question box.
 *
 * MVP: detect intent (query vs data-edit) locally via keyword heuristics, then:
 *  - If query: keep existing /query behavior (handled by main.js)
 *  - If edit: call a backend intent endpoint (to be implemented) OR
 *            fall back to /data/* endpoints directly based on heuristics.
 *
 * For now, this file is intentionally minimal and will only be wired after
 * backend intent endpoint is implemented.
 */

window.DATA_AGENT_READY = true;

