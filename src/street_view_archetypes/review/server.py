from __future__ import annotations

import json
import mimetypes
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pandas as pd

from street_view_archetypes.config import load_pipeline_config


def run_review_server(config_path: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    config = load_pipeline_config(config_path)
    manifest_path = config.imagery.local_manifest_path
    if manifest_path is None:
        raise ValueError("Config does not define imagery.local_manifest_path.")
    if not manifest_path.exists():
        raise ValueError(f"Manifest not found: {manifest_path}")

    store = ReviewStore(
        manifest_path=manifest_path,
        categories=config.classification.target_categories,
    )
    server = ReviewHTTPServer((host, port), ReviewHandler)
    server.store = store
    server.rubric = build_rubric(config.classification.target_categories)
    print(f"[street-view-archetypes] Review server running at http://{host}:{port}", flush=True)
    print(f"[street-view-archetypes] Saving updates directly to {manifest_path}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[street-view-archetypes] Review server stopped.", flush=True)
    finally:
        server.server_close()


class ReviewStore:
    def __init__(self, manifest_path: Path, categories: list[str]) -> None:
        self.manifest_path = manifest_path
        self.categories = categories
        self._lock = threading.Lock()
        self._df = pd.read_csv(manifest_path).fillna("")
        for column in ("reviewed_categories", "review_notes", "source_labels", "image_path", "review_status"):
            if column not in self._df.columns:
                self._df[column] = ""
        self._df["reviewed_categories"] = self._df["reviewed_categories"].apply(_normalize_reviewed_categories_value)
        self._df["review_status"] = self._df.apply(_normalize_review_status_row, axis=1)

    def records(self) -> list[dict[str, Any]]:
        with self._lock:
            records: list[dict[str, Any]] = []
            for index, row in enumerate(self._df.to_dict(orient="records")):
                records.append(
                    {
                        "index": index,
                        "sample_id": row.get("sample_id", ""),
                        "heading": row.get("heading", ""),
                        "stratum": row.get("stratum", ""),
                        "image_path": row.get("image_path", ""),
                        "source_labels": row.get("source_labels", ""),
                        "reviewed_categories": _split_pipe(row.get("reviewed_categories", "")),
                        "review_status": row.get("review_status", "unreviewed"),
                        "review_notes": row.get("review_notes", ""),
                    }
                )
            return records

    def summary(self) -> dict[str, Any]:
        with self._lock:
            reviewed = self._df["review_status"].astype(str).str.strip().str.lower() == "reviewed"
            with_images = self._df["image_path"].astype(str).str.strip() != ""
            return {
                "row_count": int(len(self._df)),
                "reviewed_row_count": int(reviewed.sum()),
                "image_row_count": int(with_images.sum()),
                "remaining_row_count": int((with_images & ~reviewed).sum()),
                "categories": self.categories,
            }

    def update_record(self, index: int, reviewed_categories: list[str], review_notes: str) -> dict[str, Any]:
        normalized_categories = [value for value in reviewed_categories if value in self.categories]
        with self._lock:
            if index < 0 or index >= len(self._df):
                raise IndexError("Record index out of range.")
            self._df.at[index, "reviewed_categories"] = "|".join(normalized_categories)
            self._df.at[index, "review_status"] = "reviewed"
            self._df.at[index, "review_notes"] = review_notes
            self._df.to_csv(self.manifest_path, index=False)
            return {
                "index": index,
                "reviewed_categories": normalized_categories,
                "review_notes": review_notes,
            }


class ReviewHTTPServer(ThreadingHTTPServer):
    store: ReviewStore
    rubric: dict[str, str]


class ReviewHandler(BaseHTTPRequestHandler):
    server: ReviewHTTPServer

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send_html(render_index_html(self.server.rubric))
            return
        if parsed.path == "/api/manifest":
            self._send_json(
                {
                    "records": self.server.store.records(),
                    "summary": self.server.store.summary(),
                }
            )
            return
        if parsed.path == "/image":
            self._send_image(parsed.query)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/api/save":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        result = self.server.store.update_record(
            index=int(payload["index"]),
            reviewed_categories=list(payload.get("reviewed_categories", [])),
            review_notes=str(payload.get("review_notes", "")),
        )
        self._send_json({"ok": True, "result": result, "summary": self.server.store.summary()})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_image(self, query: str) -> None:
        params = urllib.parse.parse_qs(query)
        image_path = Path(params.get("path", [""])[0])
        if not image_path.is_absolute() or not image_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type, _ = mimetypes.guess_type(image_path.name)
        payload = image_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _split_pipe(value: str) -> list[str]:
    return [token.strip() for token in str(value).split("|") if token.strip()]


def _normalize_reviewed_categories_value(value: object) -> str:
    normalized = str(value).strip()
    if normalized in {"", "[]", "[ ]", "null", "None"}:
        return ""
    return normalized


def _normalize_review_status_row(row: pd.Series) -> str:
    status = str(row.get("review_status", "")).strip().lower()
    if status in {"reviewed", "unreviewed"}:
        return status
    categories = _normalize_reviewed_categories_value(row.get("reviewed_categories", ""))
    return "reviewed" if categories else "unreviewed"


INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Street View Archetypes Review</title>
  <style>
    :root {
      --bg: #f3f5f7;
      --panel: rgba(255, 255, 255, 0.92);
      --panel-strong: #ffffff;
      --ink: #101418;
      --muted: #66707b;
      --muted-soft: #8a939d;
      --line: #dde3e8;
      --line-strong: #c8d1d8;
      --accent: #0f766e;
      --accent-soft: #e5f4f1;
      --accent-strong: #0b5d56;
      --danger: #b42318;
      --shadow: 0 18px 48px rgba(15, 23, 42, 0.08);
      --radius-xl: 28px;
      --radius-lg: 22px;
      --radius-md: 16px;
      --radius-sm: 12px;
    }
    body {
      margin: 0;
      font-family: "Avenir Next", "Helvetica Neue", Helvetica, Arial, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.08) 0, transparent 28%),
        radial-gradient(circle at top right, rgba(15, 23, 42, 0.05) 0, transparent 26%),
        linear-gradient(180deg, #fafbfc 0%, var(--bg) 100%);
    }
    .shell {
      max-width: 1380px;
      margin: 0 auto;
      padding: 28px;
      display: grid;
      grid-template-columns: minmax(0, 1.45fr) minmax(360px, 0.95fr);
      gap: 24px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow);
      overflow: hidden;
      backdrop-filter: blur(18px);
    }
    .image-wrap {
      aspect-ratio: 1.18 / 1;
      background:
        linear-gradient(180deg, rgba(236, 240, 243, 0.96) 0%, rgba(228, 233, 238, 0.96) 100%);
      display: grid;
      place-items: center;
      border-bottom: 1px solid var(--line);
    }
    img {
      width: 100%;
      height: 100%;
      object-fit: contain;
      background: #eef2f5;
    }
    .meta {
      padding: 22px 24px 24px;
    }
    .controls {
      padding: 26px 24px 24px;
      display: flex;
      flex-direction: column;
      min-height: 100%;
      box-sizing: border-box;
    }
    .eyebrow {
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-size: 11px;
      font-weight: 700;
      color: var(--muted);
    }
    h1 {
      margin: 10px 0 0;
      font-size: 34px;
      line-height: 1.05;
      letter-spacing: -0.03em;
      font-weight: 700;
    }
    .subhead {
      margin-top: 10px;
      font-size: 15px;
      line-height: 1.55;
      color: var(--muted);
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }
    .stat {
      padding: 14px 16px;
      border-radius: var(--radius-md);
      background: #f7f9fb;
      border: 1px solid var(--line);
      font-size: 14px;
      line-height: 1.35;
      color: var(--muted);
    }
    .stat strong {
      display: block;
      margin-bottom: 4px;
      font-size: 24px;
      line-height: 1;
      letter-spacing: -0.03em;
      color: var(--ink);
      font-weight: 700;
    }
    .meta-grid {
      display: grid;
      gap: 14px;
      margin-top: 18px;
    }
    .meta-card {
      padding: 14px 16px;
      border-radius: var(--radius-md);
      background: var(--panel-strong);
      border: 1px solid var(--line);
    }
    .meta-card-title {
      margin-bottom: 8px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted-soft);
    }
    .meta-card-body {
      font-size: 15px;
      line-height: 1.5;
      color: var(--ink);
    }
    .path {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      line-height: 1.55;
      color: var(--muted);
      word-break: break-all;
    }
    .button-row {
      display: flex;
      gap: 12px;
      margin-top: 14px;
    }
    button {
      border: 1px solid transparent;
      border-radius: 999px;
      padding: 13px 18px;
      min-height: 48px;
      background: var(--accent);
      color: white;
      font: inherit;
      font-size: 15px;
      font-weight: 600;
      letter-spacing: 0.01em;
      cursor: pointer;
      transition: transform 120ms ease, background 120ms ease, border-color 120ms ease, opacity 120ms ease;
    }
    button:hover:not(:disabled) {
      transform: translateY(-1px);
      background: var(--accent-strong);
    }
    button.secondary {
      background: #ffffff;
      border-color: var(--line-strong);
      color: var(--ink);
    }
    button.secondary:hover:not(:disabled) {
      background: #f7fafb;
      border-color: var(--muted-soft);
    }
    button:disabled {
      opacity: 0.42;
      cursor: not-allowed;
      transform: none;
    }
    .chips {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin: 0;
    }
    label.chip {
      border: 1px solid var(--line-strong);
      border-radius: 999px;
      padding: 10px 14px;
      display: flex;
      gap: 8px;
      align-items: center;
      background: #ffffff;
      font-size: 14px;
      font-weight: 600;
      color: var(--ink);
      min-height: 44px;
      box-sizing: border-box;
    }
    label.chip input {
      accent-color: var(--accent);
      inline-size: 18px;
      block-size: 18px;
    }
    textarea {
      width: 100%;
      min-height: 150px;
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      padding: 14px 16px;
      font: inherit;
      font-size: 15px;
      line-height: 1.55;
      background: #fbfcfd;
      box-sizing: border-box;
      resize: vertical;
    }
    textarea:focus {
      outline: 2px solid rgba(15, 118, 110, 0.16);
      border-color: rgba(15, 118, 110, 0.45);
    }
    .status {
      margin-top: 16px;
      color: var(--accent);
      min-height: 22px;
      font-size: 14px;
      font-weight: 600;
    }
    .rubric {
      margin: 22px 0 18px;
      padding: 16px 18px;
      border-radius: var(--radius-md);
      background: linear-gradient(180deg, #f1faf8 0%, var(--accent-soft) 100%);
      border: 1px solid #c7e5df;
      font-size: 14px;
      line-height: 1.6;
    }
    .rubric strong {
      display: block;
      margin-bottom: 8px;
      font-size: 13px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .error {
      color: var(--danger);
      font-weight: 600;
      margin-top: 16px;
      white-space: pre-wrap;
      font-size: 14px;
      line-height: 1.45;
    }
    .controls-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
    }
    .record-pill {
      padding: 10px 12px;
      border-radius: 999px;
      background: #f4f7f9;
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
      white-space: nowrap;
    }
    .section-label {
      margin: 24px 0 10px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted-soft);
    }
    .notes-wrap {
      margin-top: 6px;
    }
    .action-card {
      margin-top: 18px;
      padding: 16px;
      border-radius: var(--radius-lg);
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(246, 249, 251, 0.98) 100%);
    }
    .action-topline {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
      margin-bottom: 12px;
    }
    .action-hint {
      font-size: 13px;
      color: var(--muted);
    }
    .action-card .section-label {
      margin: 0;
    }
    .action-cluster {
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .status-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-top: 8px;
    }
    @media (max-width: 1080px) {
      .shell {
        grid-template-columns: 1fr;
      }
      .stats {
        grid-template-columns: 1fr;
      }
    }
    @media (max-width: 920px) {
      .shell {
        padding: 16px;
        gap: 16px;
      }
      h1 {
        font-size: 28px;
      }
      .button-row {
        flex-direction: column;
      }
      .action-topline,
      .status-row {
        flex-direction: column;
        align-items: stretch;
      }
      button {
        width: 100%;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="panel">
      <div class="image-wrap"><img id="review-image" alt="Review image"></div>
      <div class="meta">
        <div class="eyebrow">Review Workspace</div>
        <h1 id="title">Loading…</h1>
        <div class="subhead">Use the current rubric to decide whether this image belongs in the active category set.</div>
        <div class="stats">
          <div class="stat"><strong id="summary-total"></strong><span>Total rows</span></div>
          <div class="stat"><strong id="summary-reviewed"></strong><span>Reviewed</span></div>
          <div class="stat"><strong id="summary-remaining"></strong><span>Remaining</span></div>
        </div>
        <div class="meta-grid">
          <div class="meta-card">
            <div class="meta-card-title">Source Labels</div>
            <div class="meta-card-body" id="source-labels"></div>
          </div>
          <div class="meta-card">
            <div class="meta-card-title">Image Path</div>
            <div class="meta-card-body path" id="image-path"></div>
          </div>
        </div>
      </div>
    </section>

    <aside class="panel">
      <div class="controls">
        <div class="controls-header">
          <div>
            <div class="eyebrow">Labeling</div>
            <h1 id="record-label">Record</h1>
          </div>
          <div class="record-pill" id="record-pill">0 / 0</div>
        </div>
        <div class="rubric">
          <strong>{{RUBRIC_TITLE}}</strong>
          {{RUBRIC_BODY}}
        </div>
        <div class="notes-wrap">
          <div class="section-label">Review Notes</div>
          <textarea id="review-notes" placeholder="Optional review notes"></textarea>
        </div>
        <div class="action-card">
          <div class="action-topline">
            <div class="section-label">Quick Label</div>
            <div class="action-hint">Tag, then move on</div>
          </div>
          <div class="action-cluster">
            <div class="chips" id="category-chips"></div>
            <div class="button-row">
              <button class="secondary" id="prev-button">Previous</button>
              <button id="next-button">Next</button>
              <button class="secondary" id="next-unreviewed-button">Next Unreviewed</button>
            </div>
          </div>
          <div class="status-row">
            <div class="status" id="status"></div>
          </div>
        </div>
        <div class="error" id="error"></div>
      </div>
    </aside>
  </div>
  <script>
    let state = { records: [], summary: {}, index: 0 };

    async function loadManifest() {
      try {
        const response = await fetch('/api/manifest');
        if (!response.ok) {
          throw new Error(`Manifest request failed: ${response.status}`);
        }
        const payload = await response.json();
        if (!payload.records || !payload.records.length) {
          throw new Error('Manifest loaded but contains no records.');
        }
        state.records = payload.records;
        state.summary = payload.summary;
        if (typeof state.index !== 'number' || state.index < 0) {
          state.index = 0;
        }
        if (state.index >= state.records.length) {
          state.index = 0;
        }
        clearError();
        render();
      } catch (error) {
        showError(error.message || String(error));
      }
    }

    function render() {
      const record = state.records[state.index];
      if (!record) {
        showError('No review record is available at the current index.');
        return;
      }

      document.getElementById('title').textContent = `${record.sample_id} • heading ${record.heading}`;
      document.getElementById('record-label').textContent = `Record ${state.index + 1} of ${state.records.length}`;
      document.getElementById('record-pill').textContent = `${state.index + 1} / ${state.records.length}`;
      const image = document.getElementById('review-image');
      image.src = `/image?path=${encodeURIComponent(record.image_path || '')}`;
      image.onerror = () => showError(`Could not load image:\\n${record.image_path || '(blank path)'}`);
      image.onload = () => clearError();
      document.getElementById('image-path').textContent = record.image_path || 'No image path';
      document.getElementById('source-labels').textContent = `Source labels: ${record.source_labels || 'none'}`;
      document.getElementById('review-notes').value = record.review_notes || '';
      document.getElementById('summary-total').textContent = `${state.summary.row_count}`;
      document.getElementById('summary-reviewed').textContent = `${state.summary.reviewed_row_count}`;
      document.getElementById('summary-remaining').textContent = `${state.summary.remaining_row_count}`;
      document.getElementById('prev-button').disabled = state.index === 0;
      document.getElementById('next-button').disabled = state.index >= state.records.length - 1;
      document.getElementById('next-unreviewed-button').disabled = nextUnreviewedIndex() === null;

      const chips = document.getElementById('category-chips');
      chips.innerHTML = '';
      for (const category of state.summary.categories) {
        const label = document.createElement('label');
        label.className = 'chip';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.value = category;
        input.checked = (record.reviewed_categories || []).includes(category);
        label.appendChild(input);
        label.appendChild(document.createTextNode(category));
        chips.appendChild(label);
      }
    }

    async function saveCurrent() {
      try {
        const inputs = Array.from(document.querySelectorAll('#category-chips input:checked'));
        const reviewed_categories = inputs.map((input) => input.value);
        const review_notes = document.getElementById('review-notes').value;
        const response = await fetch('/api/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ index: state.index, reviewed_categories, review_notes })
        });
        if (!response.ok) {
          throw new Error(`Save failed: ${response.status}`);
        }
        const payload = await response.json();
        state.records[state.index].reviewed_categories = reviewed_categories;
        state.records[state.index].review_notes = review_notes;
        state.records[state.index].review_status = 'reviewed';
        state.summary = payload.summary;
        document.getElementById('status').textContent = 'Saved';
        clearError();
        return true;
      } catch (error) {
        showError(error.message || String(error));
        return false;
      }
    }

    async function step(delta) {
      const nextIndex = Math.max(0, Math.min(state.records.length - 1, state.index + delta));
      if (nextIndex === state.index) {
        render();
        return;
      }
      const saved = await saveCurrent();
      if (!saved) {
        return;
      }
      state.index = nextIndex;
      document.getElementById('status').textContent = 'Saved and moved';
      render();
    }

    function nextUnreviewedIndex() {
      for (let i = state.index + 1; i < state.records.length; i += 1) {
        if ((state.records[i].review_status || 'unreviewed') !== 'reviewed') {
          return i;
        }
      }
      return null;
    }

    async function nextUnreviewed() {
      const targetIndex = nextUnreviewedIndex();
      if (targetIndex === null) {
        document.getElementById('status').textContent = 'No later unreviewed records';
        render();
        return;
      }
      const saved = await saveCurrent();
      if (!saved) {
        return;
      }
      state.index = targetIndex;
      document.getElementById('status').textContent = 'Saved and moved to next unreviewed record';
      clearError();
      render();
    }

    function showError(message) {
      document.getElementById('error').textContent = message;
    }

    function clearError() {
      document.getElementById('error').textContent = '';
    }

    document.getElementById('prev-button').addEventListener('click', () => step(-1));
    document.getElementById('next-button').addEventListener('click', () => step(1));
    document.getElementById('next-unreviewed-button').addEventListener('click', nextUnreviewed);
    loadManifest();
  </script>
</body>
</html>
"""


def build_rubric(categories: list[str]) -> dict[str, str]:
    primary = categories[0] if categories else ""
    if primary == "arterial_roadways":
        return {
            "title": "Arterial roadways rubric",
            "body": (
                "Label <code>arterial_roadways</code> when the image is primarily a major roadway scene with clear through-movement function, "
                "such as multiple travel lanes, turn lanes, medians, wide intersections, commercial frontages, or other cues of an arterial street. "
                "Do not label it when the view is mainly a local residential street, cul-de-sac, driveway, parking aisle, or when the arterial character is not visually legible. "
                "If your study is targeting midblock through segments specifically, exclude signal-dominated intersections and approach views with strong turn-pocket or stop-bar geometry."
            ),
        }
    return {
        "title": "Housing units rubric",
        "body": (
            "Label <code>housing_units</code> when the image is primarily a residential scene and the housing form is visually legible. "
            "Multiple houses are fine. Do not label it when housing is only incidental, distant, obscured, or when the scene is mainly roadway, parking, open space, walls, or commercial frontage."
        ),
    }


def render_index_html(rubric: dict[str, str]) -> str:
    return (
        INDEX_HTML.replace("{{RUBRIC_TITLE}}", rubric["title"])
        .replace("{{RUBRIC_BODY}}", rubric["body"])
    )
