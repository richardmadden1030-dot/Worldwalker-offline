"""AI client: ported 1:1 from the original Tkinter build. Talks to a local
OpenAI-compatible server (LM Studio, etc.) or OpenAI cloud, preferring the
Responses API and falling back to Chat Completions."""
import copy, json, re, socket, time, urllib.request, urllib.error
from ai_budget import AIBudgetError, reserve, consume_retry
from worlds import DEFAULT_MODEL

# $ per 1M tokens, (input, output). Anything not listed just shows token
# counts with no cost estimate rather than guessing — better an honest
# "unknown" than a made-up number. Local models are always free regardless
# of what's in here; this table only ever applies to provider == "cloud".
MODEL_PRICING_PER_1M = {
    "gpt-5-nano": (0.05, 0.40), "gpt-5-mini": (0.25, 2.00), "gpt-5": (1.25, 10.00),
    "gpt-5.1": (1.25, 10.00), "gpt-5.2": (1.75, 14.00), "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50), "gpt-5.4-nano": (0.20, 1.25), "gpt-5.5": (5.00, 30.00),
    "gpt-5.5-pro": (30.00, 180.00), "gpt-5.6-luna": (0.20, 1.20), "gpt-5.6-terra": (2.00, 12.00),
    "gpt-5.6-sol": (4.00, 20.00), "gpt-4o": (2.50, 10.00), "gpt-4o-mini": (0.15, 0.60),
}

# This is intentionally below common cloud TPM ceilings. A single enormous
# long-campaign request should never consume an account's whole rolling-minute
# allowance or strand the save with a 429 before generation begins.
CLOUD_REQUEST_SOFT_TOKEN_CAP = 80_000


def estimate_cost_usd(model, input_tokens, output_tokens):
    price = MODEL_PRICING_PER_1M.get(str(model))
    if not price:
        return None
    return (input_tokens / 1_000_000) * price[0] + (output_tokens / 1_000_000) * price[1]


def clean_json(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.I)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _close_open_json(candidate):
    """Track string/escape state and open-bracket depth through `candidate`
    and close whatever's left open. Returns a parsed dict, or None if the
    result still isn't valid JSON (most often because the tail is a
    dangling, valueless key with no colon yet — a plain close can't fix
    that; the caller backtracks past it instead)."""
    in_string, escape, stack = False, False, []
    for ch in candidate:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if stack:
                    stack.pop()
    if not stack and not in_string:
        return None  # already balanced — a normal parse already tried this exact text
    repaired = re.sub(r",\s*$", "", candidate)
    if in_string:
        repaired += '"'
    for opener in reversed(stack):
        repaired += "}" if opener == "{" else "]"
    try:
        return json.loads(repaired)
    except Exception:
        return None


def repair_truncated_json(text):
    """Best-effort recovery for a response cut off mid-generation before its
    JSON ever closed — the dominant real-world failure mode for smaller/local
    models asked to fill a large schema on a limited token budget. First
    tries simply closing whatever strings/brackets were left open; if the
    very tail is an incomplete fragment that can't be cleanly closed (e.g. a
    bare trailing key with no colon yet), backs up to the last comma and
    discards the dangling remainder, repeating until something parses. A
    salvaged narrative/state_patch missing its last field or two is far
    better than surfacing an outright error. Returns a parsed dict, or None
    if nothing recoverable was found."""
    s = clean_json(text)
    start = s.find("{")
    if start == -1:
        return None
    s = s[start:]
    result = _close_open_json(s)
    if result is not None:
        return result
    candidate = s
    for _ in range(50):  # bounded — this is a last-resort salvage, not an open-ended loop
        idx = candidate.rfind(",")
        if idx == -1:
            return None
        candidate = candidate[:idx]
        result = _close_open_json(candidate)
        if result is not None:
            return result
    return None


class AIResponseError(RuntimeError):
    """Transport succeeded but the model output was unusable."""


class AIHTTPError(RuntimeError):
    def __init__(self, status, detail, retry_after=0):
        self.status = int(status)
        self.detail = str(detail)[:1000]
        try:
            self.retry_after = max(0, float(retry_after or 0))
        except (TypeError, ValueError):
            self.retry_after = 0
        super().__init__(f"AI HTTP {status}: {self.detail[:350]}")


def classify_error(error):
    if isinstance(error, urllib.error.HTTPError):
        return AIHTTPError(error.code, error.read().decode("utf-8", errors="replace"), error.headers.get("Retry-After", 0) if error.headers else 0)
    # Older compatible subclasses may still surface typed HTTP status in text.
    if type(error) is RuntimeError:
        match = re.search(r"(?:/responses |/chat/completions )?HTTP (\d{3}): (.*)", str(error), re.S)
        if match:
            return AIHTTPError(int(match[1]), match[2])
    return error


class AI:
    def __init__(self, key="", model=DEFAULT_MODEL, provider="local",
                 base_url="http://localhost:1234/v1", local_token="", max_estimated_cost_usd=0):
        self.key = key
        self.model = model
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.local_token = local_token
        self.max_estimated_cost_usd = max(0.0, float(max_estimated_cost_usd or 0))
        self.last_endpoint = ""
        self.usage = {"input_tokens": 0, "cached_input_tokens": 0, "uncached_input_tokens": 0,
                      "output_tokens": 0, "calls": 0, "cost_usd": 0.0,
                      "cost_unknown": False, "cost_is_conservative": False, "by_task": {}}

    def estimate_request_cost(self, instructions, payload, max_output_tokens=700):
        """Conservative preflight estimate; local models always return zero."""
        if self.provider != "cloud":
            return 0.0
        price = MODEL_PRICING_PER_1M.get(str(self.model))
        if not price:
            return None
        raw = str(instructions or "") + json.dumps(payload or {}, ensure_ascii=False, default=str)
        estimated_input = max(1, len(raw) // 4)
        return (estimated_input / 1_000_000) * price[0] + (max(1, int(max_output_tokens or 700)) / 1_000_000) * price[1]

    @staticmethod
    def _request_token_estimate(instructions, payload, max_output_tokens=700):
        raw = str(instructions or "") + json.dumps(payload or {}, ensure_ascii=False, default=str)
        return max(1, len(raw) // 4) + max(1, int(max_output_tokens or 700))

    def _bounded_cloud_payload(self, instructions, payload, max_output_tokens=700, token_cap=None):
        """Last-resort transport cap for any caller that missed local trimming.

        Normal game turns are already relevance-budgeted before they reach the
        client. This defensive layer handles old saves and unusual routes by
        reducing only request copies, never the real campaign state.
        """
        cap = max(20_000, int(token_cap or CLOUD_REQUEST_SOFT_TOKEN_CAP))
        estimate = self._request_token_estimate(instructions, payload, max_output_tokens)
        if estimate <= cap or not isinstance(payload, dict):
            return payload
        bounded = copy.deepcopy(payload)
        state = bounded.get("state_before") if isinstance(bounded.get("state_before"), dict) else None
        target = state if state is not None else bounded
        protected = {
            "name", "world", "difficulty", "location", "world_time", "canon_day", "canon_anchor",
            "stats", "hidden_stats", "hp", "hp_max", "resource", "resource_max", "resource_name",
            "skills", "special", "class_profile", "equipment", "combat", "danger_scenario",
            "live_scene", "scene_state", "grounding_packet", "mechanical_power_profile",
            "capability_summary", "active_scenario", "simulation_context", "prompt_budget",
        }

        def compact(value, depth=0):
            if isinstance(value, str):
                limit = 900 if depth > 1 else 1800
                return value if len(value) <= limit else value[:limit].rstrip() + "…"
            if isinstance(value, list):
                source = value[-(8 if depth > 1 else 14):]
                return [compact(item, depth + 1) for item in source]
            if isinstance(value, dict):
                items = list(value.items())
                if len(items) > (18 if depth > 1 else 30):
                    items = items[-(18 if depth > 1 else 30):]
                return {str(key): compact(item, depth + 1) for key, item in items}
            return value

        for key in list(target):
            if key not in protected and isinstance(target[key], (dict, list, str)):
                target[key] = compact(target[key])
        estimate = self._request_token_estimate(instructions, bounded, max_output_tokens)
        if estimate > cap:
            def size(item):
                try:
                    return len(json.dumps(item, ensure_ascii=False, default=str))
                except Exception:
                    return len(repr(item))
            for _, key in sorted(((size(value), key) for key, value in target.items()
                                  if key not in protected), reverse=True):
                if estimate <= cap:
                    break
                target.pop(key, None)
                estimate = self._request_token_estimate(instructions, bounded, max_output_tokens)
        self.usage["request_compactions"] = int(self.usage.get("request_compactions", 0) or 0) + 1
        self.usage["last_request_token_estimate"] = estimate
        return bounded

    def _record_usage(self, data):
        """Tallies tokens from a raw API response, before any JSON-content
        parsing — a call that spent tokens but returned unparseable content
        still spent real money, so this runs first and never raises."""
        u = (data or {}).get("usage") or {}
        in_tok = int(u.get("input_tokens", u.get("prompt_tokens", 0)) or 0)
        out_tok = int(u.get("output_tokens", u.get("completion_tokens", 0)) or 0)
        details = u.get("input_tokens_details") or u.get("prompt_tokens_details") or {}
        cached_tok = min(in_tok, max(0, int(details.get("cached_tokens", 0) or 0)))
        if not in_tok and not out_tok:
            return
        self.usage["input_tokens"] += in_tok
        self.usage["cached_input_tokens"] += cached_tok
        self.usage["uncached_input_tokens"] += max(0, in_tok - cached_tok)
        self.usage["output_tokens"] += out_tok
        self.usage["calls"] += 1
        task = str(getattr(self, "_active_task", "general") or "general")
        task_row = self.usage.setdefault("by_task", {}).setdefault(task, {
            "calls": 0, "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
        task_row["calls"] += 1; task_row["input_tokens"] += in_tok
        task_row["cached_input_tokens"] += cached_tok; task_row["output_tokens"] += out_tok
        if self.provider != "cloud":
            return
        # The local price table intentionally stores only standard input and
        # output rates. Providers can discount cached input differently by
        # model, so keep the displayed dollar total conservative while still
        # exposing exactly how many cached tokens the API reported.
        self.usage["cost_is_conservative"] = bool(self.usage.get("cost_is_conservative") or cached_tok)
        cost = estimate_cost_usd(self.model, in_tok, out_tok)
        if cost is None:
            self.usage["cost_unknown"] = True
        else:
            self.usage["cost_usd"] += cost
            task_row["cost_usd"] += cost

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.provider == "cloud":
            if self.key:
                h["Authorization"] = f"Bearer {self.key}"
        elif self.local_token:
            h["Authorization"] = f"Bearer {self.local_token}"
        return h

    def endpoint(self, path):
        if self.provider == "cloud":
            return "https://api.openai.com/v1" + path
        return self.base_url + path

    def list_models(self, timeout=8):
        req = urllib.request.Request(self.endpoint("/models"), headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [x.get("id", "") for x in data.get("data", []) if x.get("id")]

    def _parse_json_payload(self, text):
        text = text.strip()
        if not text:
            raise AIResponseError("The AI server returned no usable text.")
        try:
            return json.loads(clean_json(text))
        except Exception:
            m = re.search(r"\{.*\}", text, re.S)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    pass
            repaired = repair_truncated_json(text)
            if repaired is not None:
                return repaired
            if self.provider == "cloud":
                raise AIResponseError(
                    "The model responded, but its response was cut off or malformed before it finished writing valid JSON "
                    "(often just an oversized reply for the request's token budget). This is usually a one-off — try again.\n\n"
                    + text[:1000]
                )
            raise AIResponseError(
                "The local model responded, but did not return valid structured JSON.\n\n"
                "Try an instruction/chat model with good JSON compliance, or lower the model temperature in the local server.\n\n"
                + text[:1000]
            )

    def _reserve_transport(self, body):
        if self.provider != "cloud":
            reserve(0.0)
            return
        price = MODEL_PRICING_PER_1M.get(str(self.model))
        estimate = None
        if price:
            input_size = len(json.dumps({k: v for k, v in body.items() if k not in {"max_tokens", "max_output_tokens"}}, ensure_ascii=False))
            output = int(body.get("max_output_tokens", body.get("max_tokens", 700)))
            estimate = (max(1, input_size // 4) * price[0] + max(1, output) * price[1]) / 1_000_000
        reserve(estimate)

    def _post_responses(self, body, timeout):
        self._reserve_transport(body)
        req = urllib.request.Request(
            self.endpoint("/responses"),
            data=json.dumps(body).encode("utf-8"),
            headers=self._headers(),
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _responses_request(self, instructions, payload, timeout, max_output_tokens=700):
        input_text = json.dumps(payload, ensure_ascii=False)
        body = {
            "model": self.model,
            "instructions": instructions,
            "input": input_text,
            "max_output_tokens": int(max_output_tokens)
        }
        # Cap hidden reasoning effort: reasoning-capable models (gpt-5.x,
        # o-series) can otherwise spend the entire max_output_tokens budget on
        # an invisible "reasoning" output item and never emit the actual
        # answer text. Plain models (gpt-4o-mini, etc.) reject this field
        # outright with a 400 rather than ignoring it, so it's only sent once
        # we know the model accepts it; a model that has already rejected it
        # is remembered for the life of this client so we stop retrying.
        if getattr(self, "_reasoning_param_ok", True):
            body["reasoning"] = {"effort": "low" if str(self.model).startswith("gpt-5.6") else "minimal"}
        # Ask the API itself to guarantee a JSON object rather than relying
        # purely on prompt instructions + best-effort text parsing — cuts
        # down on the rare "wrote prose instead of JSON" failure mode. Same
        # feature-detect-and-remember pattern as the reasoning param above,
        # since not every endpoint claiming Responses-API compatibility
        # actually implements this field.
        if getattr(self, "_json_mode_ok", True):
            body["text"] = {"format": {"type": "json_object"}}
            # OpenAI requires the literal word "json" to appear somewhere in
            # the input when text.format is json_object — specifically in
            # "input" (per its own error's "param": "input"), not just
            # anywhere in the request. The payload's field names/values won't
            # reliably contain it, so guarantee it rather than gamble on the
            # 400-and-retry path ever being needed.
            if "json" not in input_text.lower():
                body["input"] = input_text + "\n\n(Respond with a single JSON object.)"
        try:
            data = self._post_responses(body, timeout)
        except urllib.error.HTTPError as e:
            details = e.read().decode("utf-8", errors="replace")
            retry_needed = False
            if e.code == 400 and "reasoning" in details.lower() and "reasoning" in body:
                self._reasoning_param_ok = False
                del body["reasoning"]
                retry_needed = True
            if e.code == 400 and ("text" in details.lower() or "json_object" in details.lower()) and "text" in body:
                self._json_mode_ok = False
                del body["text"]
                retry_needed = True
            if retry_needed:
                consume_retry()
                data = self._post_responses(body, timeout)
            else:
                raise AIHTTPError(e.code, details, e.headers.get("Retry-After", 0) if e.headers else 0)
        self._record_usage(data)
        parts = []
        for item in data.get("output", []):
            if item.get("type") == "message":
                for c in item.get("content", []):
                    if c.get("type") in ("output_text", "text"):
                        parts.append(c.get("text", ""))
        if not parts and isinstance(data.get("output_text"), str):
            parts.append(data["output_text"])
        self.last_endpoint = "/responses"
        return self._parse_json_payload("\n".join(parts))

    def _chat_request(self, instructions, payload, timeout, max_output_tokens=700):
        user_content = json.dumps(payload, ensure_ascii=False)
        # Same requirement as the Responses API path: the word "json" must
        # appear somewhere in the messages to use response_format
        # json_object. gm_rules-based instructions already end in "Return
        # ONLY valid JSON", but not every caller uses gm_rules, so guarantee
        # it here too rather than depend on that.
        if "json" not in instructions.lower() and "json" not in user_content.lower():
            user_content += "\n\n(Respond with a single JSON object.)"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.55,
            "max_tokens": int(max_output_tokens),
        }
        # Many local OpenAI-compatible servers (LM Studio, Ollama, vLLM) also
        # implement response_format json_object — worth asking for it the
        # same way the cloud path does, but a server that rejects the field
        # outright gets it dropped and remembered so every later call in
        # this session doesn't pay for the same failed request twice.
        if getattr(self, "_json_mode_ok", True):
            body["response_format"] = {"type": "json_object"}
        def _send(payload_body):
            self._reserve_transport(payload_body)
            req = urllib.request.Request(
                self.endpoint("/chat/completions"),
                data=json.dumps(payload_body).encode("utf-8"),
                headers=self._headers(),
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        try:
            data = _send(body)
        except urllib.error.HTTPError as e:
            details = e.read().decode("utf-8", errors="replace")
            if e.code == 400 and "response_format" in body and ("response_format" in details.lower() or "json_object" in details.lower()):
                self._json_mode_ok = False
                del body["response_format"]
                consume_retry()
                data = _send(body)
            else:
                raise
        self._record_usage(data)
        choices = data.get("choices", [])
        if not choices:
            raise AIResponseError("The local chat endpoint returned no choices.")
        content = choices[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            content = "\n".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in content)
        self.last_endpoint = "/chat/completions"
        return self._parse_json_payload(str(content))

    def request(self, instructions, payload, timeout=240, max_output_tokens=700):
        self._active_task = str((payload or {}).get("task") or "general") if isinstance(payload, dict) else "general"
        # Transport receipts never belong in a narrator's context.
        def clean(value):
            if isinstance(value, dict):
                return {k: clean(v) for k, v in value.items() if k not in {"_request_receipts", "_recovery_guard", "expected_guard", "expected_campaign"}}
            if isinstance(value, list):
                return [clean(v) for v in value]
            return value
        payload = clean(payload)
        if self.provider == "cloud":
            payload = self._bounded_cloud_payload(instructions, payload, max_output_tokens)
        projected = self.estimate_request_cost(instructions, payload, max_output_tokens)
        self.usage["last_projected_cost_usd"] = round(projected, 6) if projected is not None else None
        if self.max_estimated_cost_usd and projected is not None and projected > self.max_estimated_cost_usd:
            raise AIBudgetError(f"This AI request is estimated at ${projected:.3f}, above your ${self.max_estimated_cost_usd:.3f} per-request limit.")
        if self.provider == "cloud" and not self.key:
            raise RuntimeError("Cloud mode is selected but no OpenAI API key is configured.")
        if self.provider not in {"cloud", "local"}:
            raise RuntimeError("Select a supported AI provider before resolving the turn.")
        send = self._responses_request if self.provider == "cloud" else self._chat_request
        for attempt in range(2):
            try:
                return send(instructions, payload, timeout, max_output_tokens)
            except AIBudgetError:
                raise
            except (RuntimeError, urllib.error.URLError, TimeoutError, socket.timeout, json.JSONDecodeError) as original:
                error = classify_error(original)
                retryable = isinstance(error, (AIResponseError, json.JSONDecodeError, TimeoutError, socket.timeout))
                delay = 0.25
                if isinstance(error, AIHTTPError):
                    code, detail = error.status, error.detail.lower()
                    if code in {401, 403}:
                        raise RuntimeError(f"AI HTTP {code}: authentication or access was rejected. Check the selected provider's credentials and model permissions; this was not retried.") from original
                    if code == 429 and any(word in detail for word in ("insufficient_quota", "billing", "quota exceeded", "exceeded your current quota")):
                        raise RuntimeError("AI HTTP 429: the account's quota or billing limit was reached. Resolve that account issue before retrying.") from original
                    retryable = code in {408, 429, 500, 502, 503, 504}
                    if code == 429 and re.search(r"request too large|tokens per min|\bTPM\b|input or output tokens", error.detail, re.I):
                        max_output_tokens = min(int(max_output_tokens), 1000)
                        payload = self._bounded_cloud_payload(instructions, payload, max_output_tokens, token_cap=60_000)
                        delay = 0
                    elif code == 429 or error.retry_after > 2:
                        # Do not hammer a rolling quota, or hold the UI for a long sleep.
                        raise RuntimeError(f"AI HTTP {code}: the provider asked for a pause. No immediate repeat was sent. Retry after the provider's rate-limit window has cleared.") from original
                    else:
                        delay = min(2.0, max(delay, error.retry_after))
                elif isinstance(error, urllib.error.URLError):
                    retryable = True
                if not retryable or attempt:
                    raise error from original
                consume_retry()
                if delay:
                    time.sleep(delay)
                if isinstance(error, (AIResponseError, json.JSONDecodeError)):
                    instructions = "Return ONLY a compact valid JSON object. Finish the JSON within the output limit; retain all required fields.\n\n" + instructions
                # At most one transport/output retry per call; the turn-wide
                # scope also counts feature negotiation and semantic repairs.
        raise RuntimeError("AI request failed.")
