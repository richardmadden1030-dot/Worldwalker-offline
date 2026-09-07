"use strict";
/* Network boundary and explicit, receipt-checked recovery. No automatic action
   resubmission: an unreadable response may belong to a successfully committed turn. */
const GAME_REQUEST_ROUTES = Object.freeze({
  "/api/adventures/resolve":"adventure_resolve",
  "/api/time/resolve": "time_resolve",
  "/api/combat/action": "combat_action",
  "/api/combat/narrate": "combat_narrate",
  "/api/event/respond": "event_respond",
});
const apiRecord = value => value !== null && typeof value === "object" && !Array.isArray(value);
function recoveryCampaignKey(state) {
  return state?.campaign_id || `${state?.world || ""}:${state?.name || ""}`;
}
function pendingStorageKey(state = APP.state) {
  return `worldwalker.pending.v1:${APP.account?.id || "local"}:${recoveryCampaignKey(state)}`;
}
function rememberPendingRequest(pending) {
  APP.retryRequest = pending;
  try { sessionStorage.setItem(pendingStorageKey(), JSON.stringify(pending)); } catch (_) { /* Optional. */ }
}
function restorePendingRequest(state) {
  if (APP.retryRequest && APP.retryRequest.campaign !== recoveryCampaignKey(state)) APP.retryRequest = null;
  if (!APP.retryRequest) {
    try {
      const saved = JSON.parse(sessionStorage.getItem(pendingStorageKey(state)) || "null");
      if (saved?.campaign === recoveryCampaignKey(state) && GAME_REQUEST_ROUTES[saved.path] && apiRecord(saved.payload) && saved.payload.request_id) APP.retryRequest = saved;
    } catch (_) { /* An unavailable or malformed local cache never blocks play. */ }
  }
  const notice = document.getElementById("turn-recovery-notice");
  if (notice) notice.hidden = !(APP.retryRequest || state?.last_failed_turn?.route);
}
function clearPendingRequest() {
  APP.retryRequest = null;
  try { sessionStorage.removeItem(pendingStorageKey()); } catch (_) { /* Optional. */ }
  const notice = document.getElementById("turn-recovery-notice");
  if (notice) notice.hidden = true;
}
function checkedGameResult(data) {
  const status = data?.status;
  const confirmation = apiRecord(data) && (
    (status === "lethal_confirm_required" && apiRecord(data.check)) ||
    (status === "power_goal_confirm_required" && Boolean(data.warning)) ||
    (status === "manual_roll_required" && apiRecord(data.check))
  );
  const state = data?.state;
  const resolved = apiRecord(data) && apiRecord(state) && typeof state.world === "string" &&
    Number.isFinite(state.turn) && (!Object.hasOwn(data, "story") || (Array.isArray(data.story) && data.story.every(row => apiRecord(row) && typeof row.text === "string")));
  if (!confirmation && !resolved) {
    const error = new Error("The host returned an incomplete game result. Your recovery request has been kept; use Retry to check whether the action already completed.");
    error.code = "INVALID_GAME_RESPONSE";
    throw error;
  }
  return data;
}
async function api(path, opts = {}) {
  const { allowEmpty = false, ...requestOptions } = opts;
  const headers = new Headers(opts.headers || {});
  const method = String(opts.method || "GET").toUpperCase();
  if (APP?.authToken) headers.set("Authorization", `Bearer ${APP.authToken}`);
  if (APP?.csrfToken && !["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-Worldwalker-CSRF", APP.csrfToken);
  requestOptions.headers = headers;
  let res;
  try {
    res = await fetch(path, requestOptions);
    if (APP.serverReachable === false) setHostConnectionState(true);
  } catch (cause) {
    setHostConnectionState(false, "The connection to Worldwalker was interrupted. Keep the game host running while reconnecting.");
    throw new Error("The Worldwalker host is temporarily unavailable. The outcome has not been assumed to fail.", { cause });
  }
  let data;
  try { data = res.status === 204 && allowEmpty ? {} : await res.json(); }
  catch (cause) {
    const error = new Error(res.ok
      ? "The host response could not be read. Use Retry to retrieve the completed result or safely resume the same request."
      : `The host returned HTTP ${res.status} without a readable error. Your recovery request has been kept.`, { cause });
    error.status = res.status;
    error.code = "INVALID_JSON_RESPONSE";
    throw error;
  }
  if (res.status === 401 && data?.authentication_required) openModal("modal-auth");
  if (!res.ok) {
    const error = new Error(data?.error || res.statusText || "Request failed");
    error.status = res.status;
    error.code = data?.error_code || "HTTP_ERROR";
    throw error;
  }
  if (data == null) throw new Error("The host returned no usable data. Your recovery request has been kept.");
  return data;
}
const apiGet = path => api(path);
async function recoverGameRequest(pending) {
  if (pending.campaign !== recoveryCampaignKey(APP.state)) throw new Error("This pending action belongs to another campaign. Reload the intended campaign before retrying.");
  const params = new URLSearchParams({ request_id: pending.payload.request_id, route: GAME_REQUEST_ROUTES[pending.path] });
  const receipt = await apiGet(`/api/action/status?${params}`);
  if (receipt.status === "completed") return checkedGameResult(receipt.result);
  if (receipt.status === "in_progress") throw new Error("The host is still resolving this action. It has not been sent again.");
  if (receipt.status !== "failed" && !(receipt.status === "unknown" && pending.beforeGuard &&
      receipt.guard === pending.beforeGuard && receipt.campaign === pending.campaign)) {
    throw new Error("The host could not safely match this request to the current campaign. Reload the campaign and inspect the Chronicle before submitting a new action.");
  }
  return checkedGameResult(await api(pending.path, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(pending.payload),
  }));
}
async function apiPost(path, body) {
  const retryable = Object.hasOwn(GAME_REQUEST_ROUTES, path);
  const payload = { ...(body || {}) };
  const existing = APP.retryRequest;
  if (retryable && !payload.request_id) {
    payload.request_id = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    payload.expected_campaign = recoveryCampaignKey(APP.state);
    if (APP.state?._recovery_guard) payload.expected_guard = APP.state._recovery_guard;
  }
  const isRetry = retryable && existing?.path === path && existing.payload.request_id === payload.request_id;
  const pending = isRetry ? existing : { path, payload, campaign: recoveryCampaignKey(APP.state), beforeGuard: APP.state?._recovery_guard || "" };
  if (retryable) rememberPendingRequest(pending);
  try {
    const result = isRetry ? await recoverGameRequest(pending) : await api(path, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    if (retryable || path === "/api/action/retry_failed") {
      checkedGameResult(result);
      clearPendingRequest();
    }
    if (APP.state && typeof result?._recovery_guard === "string") APP.state._recovery_guard = result._recovery_guard;
    return result;
  } catch (error) {
    if (retryable) restorePendingRequest(APP.state);
    throw error;
  }
}
const apiForm = (path, body) => api(path, { method: "POST", body });
