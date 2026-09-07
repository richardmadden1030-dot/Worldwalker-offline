"use strict";
/* Render a committed receipt. No game mutation, timers, fetches, or model calls. */
const TurnFeedback = (() => {
  function node(tag, text, className = "") {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = String(text);
    if (className) element.className = className;
    return element;
  }
  function duration(minutes) {
    if (!Number.isFinite(minutes) || minutes < 0) return "";
    if (minutes === 0) return "No time passed";
    if (minutes < 60) return `${minutes} min passed`;
    const days = Math.floor(minutes / 1440), hours = Math.floor((minutes % 1440) / 60), rest = minutes % 60;
    return [days ? `${days}d` : "", hours ? `${hours}h` : "", rest ? `${rest}m` : ""].filter(Boolean).join(" ") + " passed";
  }
  function format(value) {
    return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: 3 }) : String(value ?? "—");
  }
  function render(receipt) {
    const details = node("details", undefined, "story-entry turn-receipt");
    details.dataset.storyKind = "growth";
    details.dataset.receiptId = receipt.id || "";
    const changes = Array.isArray(receipt.changes) ? receipt.changes : [];
    const summary = node("summary");
    summary.append(node("strong", receipt.label || "Recorded outcome"), node("span", `${duration(receipt.elapsed_minutes)}${Number.isFinite(receipt.elapsed_minutes) ? " · " : ""}${changes.length} recorded change${changes.length === 1 ? "" : "s"}`, "turn-receipt-meta"));
    details.append(summary);
    const preview = node("div", undefined, "turn-receipt-preview");
    for (const change of changes.slice(0, 3)) {
      const numeric = typeof change.before === "number" && typeof change.after === "number";
      const delta = numeric ? change.after - change.before : null;
      preview.append(node("span", numeric ? `${change.label} ${delta > 0 ? "+" : ""}${format(delta)}` : `${change.label}: ${format(change.after)}`));
    }
    if (changes.length) summary.append(preview);
    const body = node("div", undefined, "turn-receipt-body");
    const table = node("dl", undefined, "turn-receipt-changes");
    for (const change of changes) {
      const row = node("div");
      row.append(node("dt", change.label), node("dd", `${format(change.before)} → ${format(change.after)}`));
      table.append(row);
    }
    body.append(changes.length ? table : node("p", "No tracked numerical or inventory changes were recorded for this outcome."));
    if (receipt.additional_changes) body.append(node("p", `${receipt.additional_changes} additional changes are available in the campaign records.`));
    if (Array.isArray(receipt.attention) && receipt.attention.length) {
      body.append(node("strong", "Still needs your attention"));
      for (const item of receipt.attention.slice(0, 3)) body.append(node("p", item, "turn-receipt-attention"));
    }
    body.append(node("small", receipt.note || "Net recorded changes; this summary does not award additional rewards."));
    details.append(body);
    return details;
  }
  return { render };
})();
