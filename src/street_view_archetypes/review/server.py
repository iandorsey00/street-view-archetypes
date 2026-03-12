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


class ReviewHandler(BaseHTTPRequestHandler):
    server: ReviewHTTPServer

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send_html(INDEX_HTML)
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
      --bg: #f4f0e8;
      --panel: #fffaf2;
      --ink: #1b1a17;
      --muted: #6b665d;
      --accent: #0f766e;
      --accent-soft: #d7efe9;
      --line: #d8d0c1;
    }
    body {
      margin: 0;
      font-family: Georgia, "Iowan Old Style", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #efe7d7 0, transparent 30%),
        linear-gradient(180deg, #f8f4ec 0%, var(--bg) 100%);
    }
    .shell {
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px;
      display: grid;
      grid-template-columns: 1.3fr 0.9fr;
      gap: 20px;
    }
    .panel {
      background: rgba(255, 250, 242, 0.95);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 18px 50px rgba(27, 26, 23, 0.08);
      overflow: hidden;
    }
    .image-wrap {
      aspect-ratio: 1 / 1;
      background: #e8e0d1;
      display: grid;
      place-items: center;
    }
    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .meta, .controls {
      padding: 18px 20px;
    }
    .eyebrow {
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 12px;
      color: var(--muted);
    }
    h1 {
      margin: 6px 0 14px;
      font-size: 28px;
    }
    .stats {
      display: flex;
      gap: 14px;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }
    .stat {
      padding: 10px 12px;
      border-radius: 12px;
      background: #f2ece2;
      font-size: 14px;
    }
    .button-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 16px;
    }
    button {
      border: 0;
      border-radius: 999px;
      padding: 10px 14px;
      background: var(--ink);
      color: white;
      font: inherit;
      cursor: pointer;
    }
    button.secondary {
      background: #e9e2d4;
      color: var(--ink);
    }
    .chips {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin: 14px 0;
    }
    label.chip {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 10px 14px;
      display: flex;
      gap: 8px;
      align-items: center;
      background: white;
    }
    textarea {
      width: 100%;
      min-height: 120px;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      font: inherit;
      background: #fffdf8;
      box-sizing: border-box;
    }
    .path {
      font-family: ui-monospace, SFMono-Regular, monospace;
      font-size: 12px;
      color: var(--muted);
      word-break: break-all;
      margin-top: 12px;
    }
    .status {
      margin-top: 12px;
      color: var(--accent);
      min-height: 20px;
    }
    .rubric {
      margin: 16px 0 18px;
      padding: 14px 16px;
      border-radius: 14px;
      background: var(--accent-soft);
      border: 1px solid #b9ddd6;
      font-size: 14px;
      line-height: 1.45;
    }
    .rubric strong {
      display: block;
      margin-bottom: 6px;
    }
    .error {
      color: #b42318;
      font-weight: 600;
      margin-top: 12px;
      white-space: pre-wrap;
    }
    @media (max-width: 920px) {
      .shell { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="panel">
      <div class="image-wrap"><img id="review-image" alt="Review image"></div>
      <div class="meta">
        <div class="eyebrow">Image Review</div>
        <h1 id="title">Loading…</h1>
        <div class="stats">
          <div class="stat" id="summary-total"></div>
          <div class="stat" id="summary-reviewed"></div>
          <div class="stat" id="summary-remaining"></div>
        </div>
        <div id="source-labels"></div>
        <div class="path" id="image-path"></div>
      </div>
    </section>

    <aside class="panel">
      <div class="controls">
        <div class="eyebrow">Labeling</div>
        <h1 id="record-label">Record</h1>
        <div class="rubric">
          <strong>Housing units rubric</strong>
          Label <code>housing_units</code> when the image is primarily a residential scene and the housing form is visually legible. Multiple houses are fine. Do not label it when housing is only incidental, distant, obscured, or when the scene is mainly roadway, parking, open space, walls, or commercial frontage.
        </div>
        <div class="chips" id="category-chips"></div>
        <textarea id="review-notes" placeholder="Optional review notes"></textarea>
        <div class="button-row">
          <button class="secondary" id="prev-button">Previous</button>
          <button class="secondary" id="next-button">Next</button>
          <button id="save-next-button">Save &amp; Next</button>
          <button class="secondary" id="save-button">Save Only</button>
          <button class="secondary" id="next-unreviewed-button">Next Unreviewed</button>
        </div>
        <div class="status" id="status"></div>
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
      const image = document.getElementById('review-image');
      image.src = `/image?path=${encodeURIComponent(record.image_path || '')}`;
      image.onerror = () => showError(`Could not load image:\\n${record.image_path || '(blank path)'}`);
      image.onload = () => clearError();
      document.getElementById('image-path').textContent = record.image_path || 'No image path';
      document.getElementById('source-labels').textContent = `Source labels: ${record.source_labels || 'none'}`;
      document.getElementById('review-notes').value = record.review_notes || '';
      document.getElementById('summary-total').textContent = `${state.summary.row_count} rows`;
      document.getElementById('summary-reviewed').textContent = `${state.summary.reviewed_row_count} reviewed`;
      document.getElementById('summary-remaining').textContent = `${state.summary.remaining_row_count} remaining`;

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

    async function saveCurrent(options = { advance: false }) {
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
        document.getElementById('status').textContent = options.advance ? 'Saved and moved to next record' : 'Saved';
        clearError();
        if (options.advance && state.index < state.records.length - 1) {
          state.index += 1;
        }
        render();
      } catch (error) {
        showError(error.message || String(error));
      }
    }

    function step(delta) {
      state.index = Math.max(0, Math.min(state.records.length - 1, state.index + delta));
      document.getElementById('status').textContent = '';
      render();
    }

    function nextUnreviewed() {
      for (let i = state.index + 1; i < state.records.length; i += 1) {
        if (!(state.records[i].reviewed_categories || []).length) {
          state.index = i;
          clearError();
          render();
          return;
        }
      }
      document.getElementById('status').textContent = 'No later unreviewed records';
    }

    function showError(message) {
      document.getElementById('error').textContent = message;
    }

    function clearError() {
      document.getElementById('error').textContent = '';
    }

    document.getElementById('prev-button').addEventListener('click', () => step(-1));
    document.getElementById('next-button').addEventListener('click', () => step(1));
    document.getElementById('save-button').addEventListener('click', () => saveCurrent({ advance: false }));
    document.getElementById('save-next-button').addEventListener('click', () => saveCurrent({ advance: true }));
    document.getElementById('next-unreviewed-button').addEventListener('click', nextUnreviewed);
    loadManifest();
  </script>
</body>
</html>
"""
