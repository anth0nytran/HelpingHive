## AI Assistant Integration Spec (MVP)

### 1) Goals (MVP)
- Q&A about the current map view (“What’s happening near me?”, “Nearest open shelter?”).
- Short viewport summary chip after pan/zoom.
- Optional: compose/classify new pins; light moderation.

Non‑goals for MVP: long chats, retrieval from external sources, tool execution.

### 2) Architecture
- Two‑step pipeline to avoid hallucinations and handle unclear questions.
  1) Intent Classifier (Gate): parses the user question → structured JSON with
     - `intent`: one of `pins|shelters|food|flood|feed311|summary|other`
     - `needs_clarification`: boolean
     - `followup_question`: short nudge to clarify
     - `filters`: `{ center:[lat,lng], radius_mi:number, categories:[], time_window_hours:number }`
  2) Answerer: builds a compact JSON context from our existing APIs (bounded by filters) and returns a concise answer strictly from that JSON.

Models: Google Gemini (server‑side). Temperature low for determinism.

### 3) Endpoints
- POST `/api/assist/qna`
  - Request: `{ question: string, center?: [lat,lng], radius_mi?: number }`
  - Response: one of
    - `{"ask": "clarifying question"}` when classifier is uncertain
    - `{"answer": "short, grounded response", "support"?: {counts...}}` when answered

- Future (optional)
  - POST `/api/assist/summary` (viewport‑only request to render chip)
  - POST `/api/assist/moderate` (score toxicity/PII before saving pin/comment)

### 4) Classifier Spec
- Model: `gemini-1.5-pro`
- Generation config:
  - `temperature: 0.1`, `top_p: 0.1`
  - `response_mime_type: application/json`
  - `response_schema`:
    ```json
    {
      "type":"object",
      "properties":{
        "intent":{"type":"string","enum":["pins","shelters","food","flood","feed311","summary","other"]},
        "needs_clarification":{"type":"boolean"},
        "followup_question":{"type":"string"},
        "filters":{
          "type":"object",
          "properties":{
            "center":{"type":"array","items":{"type":"number"},"minItems":2,"maxItems":2},
            "radius_mi":{"type":"number"},
            "categories":{"type":"array","items":{"type":"string"}},
            "time_window_hours":{"type":"number"}
          }
        }
      },
      "required":["intent","needs_clarification","followup_question","filters"]
    }
    ```
- System prompt (concise):
  - “You are a router for a disaster‑help map. Choose the best intent. If vague (no topic/location/action), set needs_clarification=true and produce a short follow‑up question. Do not answer; output JSON only.”
- Few‑shot examples (include 3–5 typical Q/outputs; keep short).

### 5) Answerer Spec
- Model: `gemini-1.5-pro`
- Generation config:
  - `temperature: 0.1`, `top_p: 0.2`
  - `response_mime_type: application/json`
  - `response_schema`:
    ```json
    {
      "type":"object",
      "properties":{
        "answer":{"type":"string"},
        "support":{"type":"object"}
      },
      "required":["answer"]
    }
    ```
- System prompt (strict grounding):
  - “You are a concise assistant for a disaster‑help map. Use ONLY the provided JSON context; never invent values. Prefer numbers, locations, and plain language. Limit to ≤ 3 sentences. If the information isn’t present, say ‘Not in data.’”

### 6) Context Builder (backend)
- Inputs: `intent`, `filters.center`, `filters.radius_mi`, `time_window_hours`.
- Data sources (existing endpoints):
  - `/api/pins` (cap 100)
  - `/api/shelters` (cap 100)
  - `/api/food` (cap 100)
  - `/api/311` (cap 100 points)
- Reduce payload:
  - Keep essential fields only (ids, lat,lng, kind/categories/status/time).
  - Clip by center + radius; filter time window if provided.
  - Add small counts (totals by category) under `support`.

### 7) Error/Unclear Handling
- If classifier `needs_clarification=true`: return `{ "ask": followup_question }`.
- If context is empty for the requested intent: return `{"answer":"Not in data."}`.

### 8) Caching & Rate Limits
- Cache key: `sha1(question|intent|roundedCenter|zoom|radius|timeWindow)`; TTL 120–180s.
- Rate limit per `anon` id: 1 request / 10s; burst 3.

### 9) Config & Secrets
- Env: `GEMINI_API_KEY=` set in hosting platform.
- Do not log requests/responses with PII.
- Keep `mcp.json` and creds out of git (already in project rules).

### 10) UI Hooks
- Q&A: small input near radius controls → POST `/api/assist/qna` with current `center`/`radius`.
- If response has `ask`, render a small follow‑up prompt; else render an answer card.
- Summary chip: on `moveend`, call with a fixed prompt like “Summarize resources visible in view,” cached by tile key.

### 11) Acceptance Criteria
- Classifier returns valid JSON 100% of the time in manual tests.
- Unclear questions produce a single sentence follow‑up (≤ 12 words).
- Answers never reference data not present in the context.
- Response times: ≤ 1.2s p50 with cache warm; ≤ 3s cold.

### 12) Implementation Checklist
1. Add dependency: `google-generativeai`.
2. Create `app/routes_ai.py` with `/api/assist/qna`.
3. Implement `classify()` and `answer()` per configs above.
4. Add context builder to fetch/cap/clip data from existing endpoints.
5. Add in‑memory (or Redis) cache + simple rate limit.
6. Wire UI: Q&A input + summary chip; handle `{ask}` vs `{answer}`.
7. Add ENV to deployment; verify logs redact content.
8. Manual test set covering: clear, unclear, empty‑data, out‑of‑scope.

### 13) Future Enhancements
- Pin compose/classify, multilingual translation, moderation scoring, dedup suggestions, push digests.


