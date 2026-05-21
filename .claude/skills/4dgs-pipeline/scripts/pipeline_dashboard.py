"""
4DGS Pipeline Dashboard
Run from the project root: python pipeline_dashboard.py
Open: http://localhost:7860
"""
import json
import re
import glob
import os
import threading
import time
from datetime import datetime
from flask import Flask, jsonify, request, Response

STATE_FILE = "pipeline_state.json"
PORT = 7860
POLL_INTERVAL = 30  # seconds

app = Flask(__name__)
_state_lock = threading.Lock()
_live_progress = {}  # in-memory progress enriched by background thread


# ── HTML template ───────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>4DGS Pipeline Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f1117; color: #e2e8f0; min-height: 100vh; padding: 32px 24px; }
  .card { background: #1a1d27; border: 1px solid #2d3148; border-radius: 12px;
          max-width: 680px; margin: 0 auto; padding: 28px 32px; }
  .header { display: flex; justify-content: space-between; align-items: flex-start;
             margin-bottom: 28px; }
  .title { font-size: 20px; font-weight: 700; color: #fff; }
  .subtitle { font-size: 13px; color: #64748b; margin-top: 4px; }
  .meta { text-align: right; font-size: 12px; color: #475569; }
  .refresh-btn { background: none; border: 1px solid #334155; color: #94a3b8;
                 border-radius: 6px; padding: 4px 10px; cursor: pointer;
                 font-size: 12px; margin-top: 6px; }
  .refresh-btn:hover { border-color: #6366f1; color: #a5b4fc; }
  .steps { display: flex; flex-direction: column; gap: 14px; }
  .step { background: #0f1117; border: 1px solid #1e2235; border-radius: 8px;
          padding: 14px 16px; }
  .step.done   { border-color: #166534; background: #052e16; }
  .step.active { border-color: #3730a3; background: #0d0d1f; }
  .step.error  { border-color: #7f1d1d; background: #1c0606; }
  .step-header { display: flex; align-items: center; gap: 10px; }
  .icon { font-size: 18px; width: 24px; flex-shrink: 0; }
  .step-label { font-size: 15px; font-weight: 600; color: #cbd5e1; }
  .step.done .step-label { color: #4ade80; }
  .step.active .step-label { color: #818cf8; }
  .step.error .step-label { color: #f87171; }
  .progress-wrap { margin-top: 12px; }
  .progress-bar-bg { background: #1e2235; border-radius: 4px; height: 8px;
                     overflow: hidden; margin-bottom: 8px; }
  .progress-bar-fill { height: 100%; border-radius: 4px;
                       background: linear-gradient(90deg, #4f46e5, #818cf8);
                       transition: width 0.4s ease; }
  .progress-meta { display: flex; justify-content: space-between;
                    font-size: 12px; color: #64748b; }
  .metrics { display: flex; gap: 16px; margin-top: 8px; flex-wrap: wrap; }
  .metric { font-size: 12px; color: #94a3b8; }
  .metric span { color: #e2e8f0; font-weight: 600; }
  .countdown { font-size: 12px; color: #475569; margin-top: 6px; }
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <div>
      <div class="title" id="proj-title">4DGS Pipeline</div>
      <div class="subtitle" id="proj-dataset">Loading...</div>
    </div>
    <div class="meta">
      <div id="last-updated">—</div>
      <button class="refresh-btn" onclick="fetchState()">↺ Refresh</button>
      <div class="countdown" id="next-refresh">Next refresh in 30s</div>
    </div>
  </div>
  <div class="steps" id="steps-container">
    <div style="color:#475569;text-align:center;padding:24px">Loading pipeline state…</div>
  </div>
</div>

<script>
let countdown = 30;
let countdownTimer = null;

const STATUS_ICON = {
  done:        '✅',
  in_progress: '🔄',
  error:       '❌',
  pending:     '⬜'
};

function pct(n) { return Math.round(n); }

function renderStep(step, progress) {
  const icon = STATUS_ICON[step.status] || '⬜';
  let extraHtml = '';

  if (step.status === 'in_progress' && progress) {
    const p = progress.percent ?? 0;
    const barWidth = Math.min(100, Math.max(0, p));
    const current = progress.current ?? 0;
    const total   = progress.total ?? 0;
    const eta     = progress.eta_minutes != null
                    ? `ETA ~${Math.round(progress.eta_minutes)} min` : '';
    const iterLabel = total > 0
                    ? `iter ${current.toLocaleString()} / ${total.toLocaleString()}` : '';

    let metricsHtml = '';
    if (progress.loss)  metricsHtml += `<div class="metric">Loss <span>${progress.loss}</span></div>`;
    if (progress.psnr)  metricsHtml += `<div class="metric">PSNR <span>${progress.psnr} dB</span></div>`;
    if (progress.files) metricsHtml += `<div class="metric">Files <span>${progress.files}</span></div>`;

    extraHtml = `
      <div class="progress-wrap">
        <div class="progress-bar-bg">
          <div class="progress-bar-fill" style="width:${barWidth}%"></div>
        </div>
        <div class="progress-meta">
          <span>${pct(p)}%  ${iterLabel}</span>
          <span>${eta}</span>
        </div>
        ${metricsHtml ? '<div class="metrics">' + metricsHtml + '</div>' : ''}
      </div>`;
  }

  return `
    <div class="step ${step.status}">
      <div class="step-header">
        <div class="icon">${icon}</div>
        <div class="step-label">${step.label}</div>
      </div>
      ${extraHtml}
    </div>`;
}

function fetchState() {
  fetch('/api/state')
    .then(r => r.json())
    .then(data => {
      document.getElementById('proj-title').textContent =
        data.project || '4DGS Pipeline';
      document.getElementById('proj-dataset').textContent =
        data.dataset ? `Dataset: ${data.dataset}` : '';
      document.getElementById('last-updated').textContent =
        'Updated ' + new Date().toLocaleTimeString();

      const container = document.getElementById('steps-container');
      const progress  = data.live_progress || {};
      container.innerHTML = (data.steps || [])
        .map(s => renderStep(s, progress[s.id]))
        .join('');

      resetCountdown();
    })
    .catch(() => {
      document.getElementById('last-updated').textContent = 'Error loading state';
    });
}

function resetCountdown() {
  clearInterval(countdownTimer);
  countdown = 30;
  updateCountdownLabel();
  countdownTimer = setInterval(() => {
    countdown--;
    updateCountdownLabel();
    if (countdown <= 0) { fetchState(); }
  }, 1000);
}

function updateCountdownLabel() {
  document.getElementById('next-refresh').textContent =
    countdown > 0 ? `Next refresh in ${countdown}s` : 'Refreshing…';
}

fetchState();
</script>
</body>
</html>"""


# ── State helpers ────────────────────────────────────────────────────────────

def read_state():
    if not os.path.exists(STATE_FILE):
        return {"project": "4DGS Pipeline", "dataset": "", "steps": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"project": "4DGS Pipeline", "dataset": "", "steps": [], "error": "state file parse error"}


def write_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ── Log / file progress detection ───────────────────────────────────────────

def _parse_training_log(log_path):
    """Return dict with current, total, percent, eta_minutes, loss, psnr."""
    if not log_path or not os.path.exists(log_path):
        return {}
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return {}

    result = {}

    # "[ITER 8000] ..." milestone lines
    iters = re.findall(r"\[ITER (\d+)\]", content)
    if iters:
        result["current"] = int(iters[-1])

    # tqdm line: "Training progress: 8000/17000 [47%, ...]"
    tqdm_matches = re.findall(r"(\d+)/(\d+)\s+\[", content)
    if tqdm_matches:
        cur, tot = tqdm_matches[-1]
        result["current"] = int(cur)
        result["total"]   = int(tot)

    # loss and PSNR from tqdm postfix or evaluation lines
    loss_m = re.findall(r"Loss[=:\s]+([\d.]+)", content)
    if loss_m:
        result["loss"] = loss_m[-1]

    psnr_m = re.findall(r"psnr[=:\s]+([\d.]+)", content, re.IGNORECASE)
    if psnr_m:
        result["psnr"] = psnr_m[-1]

    if "Training complete" in content:
        result["done"] = True
        result["percent"] = 100.0
        return result

    if result.get("current") and result.get("total"):
        cur, tot = result["current"], result["total"]
        result["percent"] = round(cur / tot * 100, 1)
        # rough ETA: estimate from typical ~0.5 it/s on 3070 Ti
        remaining = tot - cur
        result["eta_minutes"] = round(remaining / 0.5 / 60, 1)

    return result


def _count_file_progress(output_dir, pattern, expected):
    """Return percent, current, total based on file count."""
    if not output_dir or not os.path.exists(output_dir):
        return {}
    found = len(glob.glob(os.path.join(output_dir, pattern)))
    if expected and expected > 0:
        pct = round(found / expected * 100, 1)
        return {"current": found, "total": expected, "percent": pct, "files": f"{found}/{expected}"}
    return {"files": str(found)}


def _parse_compress_log(log_path):
    """Parse compression log for 'N in M' block progress."""
    if not log_path or not os.path.exists(log_path):
        return {}
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return {}
    matches = re.findall(r"(\d+)\s+in\s+(\d+)", content)
    if matches:
        cur, tot = matches[-1]
        cur, tot = int(cur), int(tot)
        return {"current": cur, "total": tot, "percent": round(cur / tot * 100, 1)}
    return {}


def refresh_live_progress(state):
    """Called by background thread. Returns dict keyed by step id."""
    progress = {}
    for step in state.get("steps", []):
        if step.get("status") != "in_progress":
            continue
        sid = step["id"]

        if sid == "train":
            p = _parse_training_log(step.get("log"))
            if p.get("done"):
                step["status"] = "done"
                write_state(state)
            else:
                progress[sid] = p

        elif sid == "export_ply":
            output_dir = step.get("output_dir", "")
            expected   = step.get("expected_files", 0)
            p = _count_file_progress(output_dir, "time_*.ply", expected)
            if p.get("current") and p["current"] >= expected > 0:
                step["status"] = "done"
                write_state(state)
            else:
                progress[sid] = p

        elif sid == "compress":
            # Try log first, fall back to file count
            p = _parse_compress_log(step.get("log"))
            if not p:
                output_dir = step.get("output_dir", "")
                expected   = step.get("expected_files", 0)
                p = _count_file_progress(output_dir, "Block*.dgsblk", expected)
            if p.get("current") and p.get("total") and p["current"] >= p["total"]:
                step["status"] = "done"
                write_state(state)
            else:
                progress[sid] = p

    return progress


# ── Background polling thread ────────────────────────────────────────────────

def _poll_loop():
    while True:
        try:
            state = read_state()
            prog  = refresh_live_progress(state)
            with _state_lock:
                _live_progress.clear()
                _live_progress.update(prog)
        except Exception as e:
            print(f"[dashboard] poll error: {e}")
        time.sleep(POLL_INTERVAL)


# ── Flask routes ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return Response(DASHBOARD_HTML, mimetype="text/html")


@app.route("/api/state")
def api_state():
    state = read_state()
    with _state_lock:
        state["live_progress"] = dict(_live_progress)
    return jsonify(state)


@app.route("/api/update", methods=["POST"])
def api_update():
    """
    Claude calls this to update a step status.
    Body: {"step_id": "train", "status": "in_progress", "log": "logs/train.log", "total_iters": 17000}
    """
    data  = request.get_json(force=True) or {}
    state = read_state()
    step_id = data.get("step_id")
    if not step_id:
        return jsonify({"error": "step_id required"}), 400

    for step in state.get("steps", []):
        if step["id"] == step_id:
            step["status"] = data.get("status", step["status"])
            for key in ("log", "total_iters", "output_dir", "expected_files"):
                if key in data:
                    step[key] = data[key]
            break

    if "dataset" in data:
        state["dataset"] = data["dataset"]

    write_state(state)
    return jsonify({"ok": True})


@app.route("/api/init", methods=["POST"])
def api_init():
    """
    Initialize fresh state for a new pipeline run.
    Body: {"project": "4DGS-Unity-VR", "dataset": "coffee_martini", "steps": [...]}
    """
    data = request.get_json(force=True) or {}
    state = {
        "project":    data.get("project", "4DGS-Unity-VR"),
        "dataset":    data.get("dataset", ""),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "steps":      data.get("steps", _default_steps(data.get("dataset", ""))),
    }
    write_state(state)
    return jsonify({"ok": True, "url": f"http://localhost:{PORT}"})


def _default_steps(dataset):
    is_dynerf = dataset in ("coffee_martini", "cook_spinach", "cut_roasted_beef",
                             "flame_salmon_1", "flame_steak", "sear_steak")
    steps = [
        {"id": "env",        "label": "Environment Setup",      "status": "pending"},
    ]
    if is_dynerf:
        steps.append({"id": "colmap", "label": "COLMAP Point Cloud", "status": "pending"})
    steps += [
        {"id": "train",      "label": "4DGS Training",           "status": "pending",
         "log": "logs/train.log",
         "total_iters": 17000 if is_dynerf else 23000},
        {"id": "export_ply", "label": "Export Per-Frame PLY",    "status": "pending",
         "output_dir": f"output/{'dynerf' if is_dynerf else 'dnerf'}/{dataset}/gaussian_pertimestamp",
         "expected_files": 300 if is_dynerf else 20},
        {"id": "compress",   "label": "Compress to .dgs",        "status": "pending",
         "output_dir": f"GSplatTest/Assets/DynGsplatData/{dataset}/Data",
         "expected_files": 15 if is_dynerf else 1,
         "log": "logs/compress.log"},
        {"id": "unity",      "label": "Unity Import & Playback", "status": "pending"},
    ]
    return steps


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    t = threading.Thread(target=_poll_loop, daemon=True)
    t.start()
    print(f"[dashboard] starting at http://localhost:{PORT}")
    print(f"[dashboard] watching state file: {os.path.abspath(STATE_FILE)}")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
