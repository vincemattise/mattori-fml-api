"""
MATTORI API — Funda floorplan proxy + Resend email proxy for Shopify.
Hosted on Railway.
"""

import json
import os
import re
import urllib.request
import urllib.error
from typing import Optional

from flask import Flask, jsonify, request
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


@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "MATTORI API", "endpoints": ["/funda-fml", "/api/send", "/api/mail"]})


@app.route("/funda-fml", methods=["POST"])
def funda_fml():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"error": "Missing URL"}), 400
    if not url.startswith("http"):
        return jsonify({"error": "URL must start with http:// or https://"}), 400

    try:
        # 1) Fetch Funda page
        page_url = normalize_url(url)
        resp = cffi_requests.get(page_url, impersonate="chrome", timeout=15)
        resp.raise_for_status()
        html = resp.text

        if "Je bent bijna op de pagina die je zoekt" in html:
            return jsonify({"error": "Funda captcha — probeer het later opnieuw"}), 200

        # 2) Extract projectId
        project_id = extract_project_id(html)
        if not project_id:
            return jsonify({"error": "Geen plattegrond (FML) gevonden voor deze woning"}), 200

        # 3) Download FML from S3
        fml_url = f"{FML_S3_BASE}/{project_id}.fml"
        fml_resp = cffi_requests.get(fml_url, impersonate="chrome", timeout=15)

        if fml_resp.status_code != 200:
            return jsonify({"error": f"FML bestand niet gevonden (status {fml_resp.status_code})"}), 200

        fml_content = fml_resp.text
        if not fml_content.strip().startswith("{"):
            return jsonify({"error": "Ongeldig FML bestand"}), 200

        return jsonify(json.loads(fml_content))

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
            "bcc": ["vince@mattori.nl"],
            "subject": subject,
            "html": html,
        }
        if to_email != "vince@mattori.nl":
            payload["reply_to"] = to_email

        result, status = _send_via_resend(payload)
        return jsonify(result), status

    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return jsonify({"error": err_body}), e.code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
