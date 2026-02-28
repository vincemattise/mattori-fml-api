"""
MATTORI API — Funda floorplan proxy + Resend email proxy for Shopify.
Hosted on Railway.
"""

import base64
import hashlib
import json
import os
import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from curl_cffi import requests as cffi_requests

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

app = Flask(__name__)

# CORS — allow Shopify + local dev
CORS(app, origins=[
    "https://mattori.nl",
    "https://www.mattori.nl",
    "https://mattori.myshopify.com",
    "http://127.0.0.1:*",
    "http://localhost:*",
])

FML_S3_BASE = "https://fmlpub.s3-eu-west-1.amazonaws.com"

FUNDA_DETAIL_ROOT = re.compile(
    r"^https?://(www\.)?funda\.nl/detail/.+/(\d+)/?",
    re.IGNORECASE
)


def normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if "/media/plattegrond/" in url:
        return url
    if FUNDA_DETAIL_ROOT.match(url):
        return url + "/media/plattegrond/1"
    return url


def extract_project_id(html: str) -> Optional[str]:
    # Method 1: Nuxt data array
    m = re.search(r'"projectId"\s*:\s*(\d+)', html)
    if m:
        idx = int(m.group(1))
        nuxt_match = re.search(r'id="__NUXT_DATA__"[^>]*>\s*(\[.+?\])\s*</script>', html, re.DOTALL)
        if nuxt_match:
            try:
                nuxt_array = json.loads(nuxt_match.group(1))
                if idx < len(nuxt_array):
                    val = nuxt_array[idx]
                    if isinstance(val, (str, int)) and re.match(r'^\d{6,}$', str(val)):
                        return str(val)
            except (json.JSONDecodeError, IndexError):
                pass

    # Method 2: embed URL
    m2 = re.search(r'projectId[=:](\d{6,})', html)
    if m2:
        return m2.group(1)

    # Method 3: S3 pattern
    m3 = re.search(r'fmlpub\.s3[^"]*?/(\d{6,})\.fml', html)
    if m3:
        return m3.group(1)

    return None


def extract_sale_status(html: str) -> Optional[str]:
    """Extract sale status from Funda page <title> tag.
    Patterns: 'te koop', 'verkocht onder voorbehoud', 'verkocht'."""
    m = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    if not m:
        return None
    title = m.group(1).lower()
    if 'verkocht onder voorbehoud' in title:
        return 'Verkocht onder voorbehoud'
    if 'verkocht' in title:
        return 'Verkocht'
    if 'te koop' in title:
        return 'Te koop'
    if 'te huur' in title:
        return 'Te huur'
    return None


@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "MATTORI API", "endpoints": ["/funda-fml", "/api/send", "/api/mail", "/api/feedback", "/upload-preview", "/preview/<id>", "/upload-fml", "/fml-file/<id>"]})


@app.route("/funda-fml", methods=["POST"])
def funda_fml():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"error": "Missing URL"}), 400
    if not url.startswith("http"):
        return jsonify({"error": "URL must start with http:// or https://"}), 400

    try:
        # 1) Fetch Funda detail page (main URL) for sale status
        base_url = url.strip().rstrip("/")
        page_url = normalize_url(url)

        # If normalize added /media/plattegrond/1, fetch main page first for title
        sale_status = None
        if page_url != base_url:
            try:
                main_resp = cffi_requests.get(base_url, impersonate="chrome", timeout=15)
                if main_resp.status_code == 200:
                    sale_status = extract_sale_status(main_resp.text)
            except Exception:
                pass  # Non-critical, continue without status

        # 2) Fetch plattegrond page for projectId
        resp = cffi_requests.get(page_url, impersonate="chrome", timeout=15)
        resp.raise_for_status()
        html = resp.text

        if "Je bent bijna op de pagina die je zoekt" in html:
            return jsonify({"error": "Funda captcha — probeer het later opnieuw"}), 200

        # Also try extracting sale status from this page if not found yet
        if not sale_status:
            sale_status = extract_sale_status(html)

        # 3) Extract projectId
        project_id = extract_project_id(html)
        if not project_id:
            return jsonify({"error": "Geen plattegrond (FML) gevonden voor deze woning"}), 200

        # 4) Download FML from S3
        fml_url = f"{FML_S3_BASE}/{project_id}.fml"
        fml_resp = cffi_requests.get(fml_url, impersonate="chrome", timeout=15)

        if fml_resp.status_code != 200:
            return jsonify({"error": f"FML bestand niet gevonden (status {fml_resp.status_code})"}), 200

        fml_content = fml_resp.text
        if not fml_content.strip().startswith("{"):
            return jsonify({"error": "Ongeldig FML bestand"}), 200

        result = json.loads(fml_content)

        if sale_status:
            result["sale_status"] = sale_status

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 200


def _send_via_resend(payload: dict):
    """Send email via Resend API. Returns (response_dict, status_code)."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=body,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "MattoriAPI/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8")), resp.status


@app.route("/api/send", methods=["POST"])
def send_email():
    """Raw proxy — caller provides full payload including HTML."""
    if not RESEND_API_KEY:
        return jsonify({"error": "RESEND_API_KEY not configured"}), 500

    data = request.get_json(force=True, silent=True) or {}
    if not data.get("from") or not data.get("to") or not data.get("html"):
        return jsonify({"error": "Missing required fields: from, to, html"}), 400

    try:
        result, status = _send_via_resend(data)
        return jsonify(result), status
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return jsonify({"error": err_body}), e.code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/mail", methods=["POST"])
def send_template_email():
    """Template-based endpoint — builds HTML server-side.
    Body: { "type": "sample"|"contact"|"verzending", "to": "email", "data": {...} }
    """
    from emails import TEMPLATES, SUBJECTS

    if not RESEND_API_KEY:
        return jsonify({"error": "RESEND_API_KEY not configured"}), 500

    body = request.get_json(force=True, silent=True) or {}
    tpl_type = body.get("type", "")
    to_email = body.get("to", "")
    data = body.get("data", {})

    if tpl_type not in TEMPLATES:
        return jsonify({"error": f"Unknown template type: {tpl_type}. Use: sample, contact, verzending"}), 400
    if not to_email:
        return jsonify({"error": "Missing 'to' field"}), 400

    try:
        html = TEMPLATES[tpl_type](data)
        subject = SUBJECTS[tpl_type](data)

        payload = {
            "from": "Vince van Mattori <vince@mattori.nl>",
            "to": [to_email],
            "bcc": ["vincekramers@icloud.com"],
            "subject": subject,
            "html": html,
        }
        if to_email.lower() != "vince@mattori.nl":
            payload["reply_to"] = to_email

        result, status = _send_via_resend(payload)
        return jsonify(result), status

    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return jsonify({"error": err_body}), e.code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/feedback", methods=["POST"])
def feedback():
    """Receive configurator feedback and email it to the team."""
    if not RESEND_API_KEY:
        return jsonify({"error": "RESEND_API_KEY not configured"}), 500

    body = request.get_json(force=True, silent=True) or {}
    message = (body.get("message") or "").strip()
    step = body.get("step", "")
    page = body.get("page", "")
    ua = body.get("ua", "")

    if not message:
        return jsonify({"error": "Missing message"}), 400

    step_line = f"<p style='color:#999;font-size:12px;margin:0 0 8px'>Stap: {step}</p>" if step else ""

    html = (
        "<div style='font-family:sans-serif;max-width:600px'>"
        f"<h2 style='margin:0 0 12px'>Maak je eigen Frame\u00B3 feedback</h2>"
        f"<p style='white-space:pre-wrap;margin:0 0 16px'>{message}</p>"
        "<hr style='border:none;border-top:1px solid #eee;margin:16px 0'>"
        f"{step_line}"
        f"<p style='color:#999;font-size:12px;margin:0'>Pagina: {page}<br>UA: {ua}</p>"
        "</div>"
    )

    try:
        result, status = _send_via_resend({
            "from": "Mattori Configurator <vince@mattori.nl>",
            "to": ["vince@mattori.nl"],
            "subject": f"Frame\u00B3 feedback \u2014 stap {step}" if step else "Frame\u00B3 feedback",
            "html": html,
        })
        return jsonify(result), status
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return jsonify({"error": err_body}), e.code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Preview screenshot storage ──
# Use Railway Volume mount if available (/data), otherwise fallback to local dir.
PREVIEW_DIR = Path(os.environ.get("PREVIEW_DIR", "/data/previews"))
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

RAILWAY_PUBLIC_URL = os.environ.get(
    "RAILWAY_PUBLIC_DOMAIN",
    "web-production-89353.up.railway.app"
)


@app.route("/upload-preview", methods=["POST"])
def upload_preview():
    """Receive base64 JPEG screenshot, save to disk, return public URL."""
    body = request.get_json(force=True, silent=True) or {}
    image_data = body.get("image", "")

    if not image_data:
        return jsonify({"error": "Missing 'image' field"}), 400

    # Strip data-URL prefix if present (e.g. "data:image/jpeg;base64,...")
    if "," in image_data:
        image_data = image_data.split(",", 1)[1]

    try:
        raw = base64.b64decode(image_data)
    except Exception:
        return jsonify({"error": "Invalid base64 data"}), 400

    # Limit size: ~5 MB max
    if len(raw) > 5 * 1024 * 1024:
        return jsonify({"error": "Image too large (max 5 MB)"}), 400

    # Generate unique filename from content hash
    file_hash = hashlib.sha256(raw).hexdigest()[:16]
    filename = f"{file_hash}.jpg"
    filepath = PREVIEW_DIR / filename

    filepath.write_bytes(raw)

    url = f"https://{RAILWAY_PUBLIC_URL}/preview/{filename}"
    return jsonify({"url": url}), 200


@app.route("/preview/<filename>")
def serve_preview(filename):
    """Serve a saved preview screenshot."""
    # Sanitize filename — only allow hex chars + .jpg
    if not re.match(r'^[a-f0-9]{16}\.jpg$', filename):
        return jsonify({"error": "Invalid filename"}), 400

    filepath = PREVIEW_DIR / filename
    if not filepath.exists():
        return jsonify({"error": "Preview not found"}), 404

    return send_file(filepath, mimetype="image/jpeg", max_age=86400 * 365)


# ── FML file storage ──
FML_DIR = Path(os.environ.get("FML_DIR", "/data/fml"))
FML_DIR.mkdir(parents=True, exist_ok=True)


@app.route("/upload-fml", methods=["POST"])
def upload_fml():
    """Receive FML JSON data, save to disk, return public URL."""
    body = request.get_json(force=True, silent=True) or {}
    fml_data = body.get("fml")

    if not fml_data:
        return jsonify({"error": "Missing 'fml' field"}), 400

    try:
        raw = json.dumps(fml_data).encode("utf-8")
    except Exception:
        return jsonify({"error": "Invalid JSON data"}), 400

    # Limit size: ~1 MB max
    if len(raw) > 1 * 1024 * 1024:
        return jsonify({"error": "FML too large (max 1 MB)"}), 400

    # Generate unique filename from content hash
    file_hash = hashlib.sha256(raw).hexdigest()[:16]
    filename = f"{file_hash}.fml"
    filepath = FML_DIR / filename

    filepath.write_bytes(raw)

    url = f"https://{RAILWAY_PUBLIC_URL}/fml-file/{filename}"
    return jsonify({"url": url}), 200


@app.route("/fml-file/<filename>")
def serve_fml(filename):
    """Serve a saved FML file."""
    if not re.match(r'^[a-f0-9]{16}\.fml$', filename):
        return jsonify({"error": "Invalid filename"}), 400

    filepath = FML_DIR / filename
    if not filepath.exists():
        return jsonify({"error": "FML not found"}), 404

    return send_file(filepath, mimetype="application/json", max_age=86400 * 365,
                     as_attachment=True, download_name=filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
