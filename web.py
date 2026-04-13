"""Flask web interface for the Mutual Funds Analyzing Tool.

Run with: python web.py
Or with gunicorn: gunicorn -w 1 -b 0.0.0.0:5000 web:app
"""

from __future__ import annotations

import os
import secrets
import threading
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path

import yaml
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from src.config import Config, load_config, validate_config
from src.pipeline import run as run_pipeline, PipelineResult
from src.utils import setup_logging

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

UPLOAD_FOLDER = Path("./uploads")
OUTPUT_FOLDER = Path("./output")
ALLOWED_EXTENSIONS = {"pdf", "xlsx", "xls"}

UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

# In-memory job tracking
jobs: dict[str, dict] = {}

# --- Auth config ---

def load_auth_config() -> dict:
    """Load auth credentials from auth.yaml."""
    auth_path = Path("auth.yaml")
    if auth_path.exists():
        with open(auth_path, "r") as f:
            return yaml.safe_load(f) or {}
    return {"username": "admin", "password": "changeme"}


def login_required(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# --- Routes ---

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        auth = load_auth_config()
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == auth.get("username") and password == auth.get("password"):
            session["authenticated"] = True
            return redirect(url_for("index"))
        flash("Invalid credentials", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template("index.html", jobs=jobs)


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        flash("No files selected", "error")
        return redirect(url_for("index"))

    # Create a unique job
    job_id = str(uuid.uuid4())[:8]
    job_dir = UPLOAD_FOLDER / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    uploaded = []
    for f in files:
        if f.filename and _allowed_file(f.filename):
            filename = secure_filename(f.filename)
            f.save(job_dir / filename)
            uploaded.append(filename)

    if not uploaded:
        flash("No valid PDF or Excel files uploaded", "error")
        return redirect(url_for("index"))

    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "files": uploaded,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "result": None,
        "output_path": None,
        "error": None,
    }

    # Run analysis in background thread
    thread = threading.Thread(target=_run_job, args=(job_id, job_dir), daemon=True)
    thread.start()

    flash(f"Job {job_id} started with {len(uploaded)} file(s)", "success")
    return redirect(url_for("job_status", job_id=job_id))


@app.route("/job/<job_id>")
@login_required
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        flash("Job not found", "error")
        return redirect(url_for("index"))
    return render_template("job.html", job=job)


@app.route("/job/<job_id>/download")
@login_required
def download(job_id: str):
    job = jobs.get(job_id)
    if not job or not job.get("output_path"):
        flash("No output file available", "error")
        return redirect(url_for("index"))

    output_path = Path(job["output_path"])
    if output_path.exists():
        return send_file(output_path, as_attachment=True, download_name=output_path.name)

    flash("Output file not found", "error")
    return redirect(url_for("job_status", job_id=job_id))


@app.route("/job/<job_id>/status-api")
@login_required
def job_status_api(job_id: str):
    """JSON endpoint for polling job status."""
    job = jobs.get(job_id)
    if not job:
        return {"error": "not found"}, 404
    return {
        "id": job["id"],
        "status": job["status"],
        "error": job.get("error"),
        "has_output": job.get("output_path") is not None,
    }


# --- Helpers ---

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _run_job(job_id: str, job_dir: Path) -> None:
    """Run the analysis pipeline for a job (in background thread)."""
    jobs[job_id]["status"] = "processing"

    try:
        setup_logging(verbose=False)

        config = load_config()
        config.input_dir = job_dir
        config.output_dir = OUTPUT_FOLDER

        errors = validate_config(config)
        if errors:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = "; ".join(errors)
            return

        result = run_pipeline(config)

        if result.output_path and result.output_path.exists():
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["output_path"] = str(result.output_path)
            jobs[job_id]["result"] = {
                "files_processed": result.files_processed,
                "funds_extracted": len(result.funds),
                "files_skipped": result.files_skipped,
                "fund_errors": result.fund_errors,
                "cli_calls": result.cli_calls,
            }
        elif result.funds:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result"] = {
                "files_processed": result.files_processed,
                "funds_extracted": len(result.funds),
                "files_skipped": result.files_skipped,
                "fund_errors": result.fund_errors,
                "cli_calls": result.cli_calls,
            }
            jobs[job_id]["error"] = "Analysis completed but Excel generation failed"
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = "No funds could be extracted from the uploaded files"

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
