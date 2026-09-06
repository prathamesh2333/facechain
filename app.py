#!/usr/bin/env python3
"""FaceChain web app.

    python app.py     ->  http://127.0.0.1:5000

Scan a face from your webcam or a file, watch the pipeline run live, and see
the on-chain record appear. If the face is nowhere on the web, the Add Face
panel appears so you can enrol it.
"""
from __future__ import annotations

import base64
import json
import queue
import threading
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_from_directory

from facechain import config
from facechain.chain import Blockchain
from facechain.localdb import LocalFaceDB
from facechain.pipeline import Pipeline

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 24 * 1024 * 1024

_pipeline: Pipeline | None = None
_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def pipeline() -> Pipeline:
    global _pipeline
    with _lock:
        if _pipeline is None:
            _pipeline = Pipeline()
    return _pipeline


def _image_from_request() -> bytes | None:
    if "image" in request.files:
        return request.files["image"].read()
    payload = request.get_json(silent=True) or {}
    b64 = payload.get("image_b64") or request.form.get("image_b64")
    if b64:
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        return base64.b64decode(b64)
    return None


# --------------------------------------------------------------------------
@app.get("/")
def index():
    p = pipeline()
    chain_info = p.chain.info() if p.chain else {"mode": "unavailable", "error": p.chain_error}
    return render_template("index.html", chain=chain_info,
                           has_serpapi=bool(config.SERPAPI_KEY),
                           enrolled=len(LocalFaceDB()))


@app.get("/api/status")
def api_status():
    p = pipeline()
    return jsonify({
        "chain": p.chain.info() if p.chain else {"mode": "unavailable"},
        "chain_error": p.chain_error,
        "records_on_chain": p.chain.total() if p.chain else 0,
        "enrolled_faces": len(LocalFaceDB()),
        "serpapi": bool(config.SERPAPI_KEY),
        "engines": [n for n, _ in __import__("facechain.search", fromlist=["x"]).available_engines()],
    })


@app.post("/api/scan")
def api_scan():
    """Kick off a scan; the browser then streams progress from /api/scan/<id>/events."""
    data = _image_from_request()
    if not data:
        return jsonify({"error": "no image supplied"}), 400
    job_id = uuid.uuid4().hex[:12]
    q: queue.Queue = queue.Queue()
    _jobs[job_id] = {"queue": q, "result": None, "image": data}

    def worker():
        def on_progress(step, message, extra):
            q.put({"type": "progress", "step": step, "message": message, "extra": extra})
        try:
            result = pipeline().scan(data, on_progress=on_progress)
            _jobs[job_id]["result"] = result.to_dict()
            q.put({"type": "done", "result": result.to_dict()})
        except Exception as exc:  # noqa: BLE001
            q.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"job_id": job_id})


@app.get("/api/scan/<job_id>/events")
def api_scan_events(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "unknown job"}), 404

    def stream():
        q: queue.Queue = job["queue"]
        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, default=str)}\n\n"

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/add-face")
def api_add_face():
    payload = request.get_json(silent=True) or {}
    job_id = payload.get("job_id")
    data = None
    if job_id and job_id in _jobs:
        data = _jobs[job_id]["image"]
    if data is None:
        data = _image_from_request()
    if not data:
        return jsonify({"ok": False, "error": "no image supplied"}), 400

    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "a name is required"}), 400
    handles = [h.strip() for h in (payload.get("handles") or "").split(",") if h.strip()]
    links = [l.strip() for l in (payload.get("links") or "").split(",") if l.strip()]
    out = pipeline().add_face(data, name=name, handles=handles, links=links,
                              notes=payload.get("notes", ""))
    return jsonify(out)


@app.get("/api/faces")
def api_faces():
    db = LocalFaceDB()
    return jsonify([e.to_dict() for e in db.all()])


@app.get("/api/faces/<entry_id>/image")
def api_face_image(entry_id: str):
    db = LocalFaceDB()
    e = db.get(entry_id)
    if not e:
        return "not found", 404
    return send_from_directory(config.FACES_DIR, e.image_file)


@app.get("/api/evidence")
def api_evidence():
    files = sorted(config.EVIDENCE_DIR.glob("*.json"), reverse=True)[:50]
    return jsonify([{"name": f.name, "size": f.stat().st_size} for f in files])


@app.post("/api/reverify")
def api_reverify():
    payload = request.get_json(silent=True) or {}
    record = payload.get("record")
    tamper = bool(payload.get("tamper"))
    if not record:
        name = payload.get("evidence")
        if not name:
            return jsonify({"error": "record or evidence filename required"}), 400
        path = config.EVIDENCE_DIR / Path(name).name
        if not path.exists():
            return jsonify({"error": "no such evidence file"}), 404
        record = json.loads(path.read_text(encoding="utf-8")).get("record")

    if tamper:
        record = json.loads(json.dumps(record))
        target = record.get("matched_post") or record.get("enrollment") or record.get("query")
        key = next(iter(target))
        target[key] = f"{target[key]}-TAMPERED"

    p = pipeline()
    if p.chain is None:
        return jsonify({"error": p.chain_error or "chain unavailable"}), 503
    out = p.chain.verify(record)
    out["tampered"] = tamper
    return jsonify(out)


if __name__ == "__main__":
    print(f"\n  FaceChain  ->  http://{config.HOST}:{config.PORT}\n")
    app.run(host=config.HOST, port=config.PORT, debug=False, threaded=True)
