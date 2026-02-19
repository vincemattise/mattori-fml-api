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
    return jsonify({"status": "ok", "service": "MATTORI API", "endpoints": ["/funda-fml", "/api/send"]})


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


@app.route("/api/send", methods=["POST"])
def send_email():
    """Proxy email sending via Resend API."""
    if not RESEND_API_KEY:
        return jsonify({"error": "RESEND_API_KEY not configured"}), 500

    data = request.get_json(force=True, silent=True) or {}

    # Validatie
    if not data.get("from") or not data.get("to") or not data.get("html"):
        return jsonify({"error": "Missing required fields: from, to, html"}), 400

    try:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "MattoriAPI/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return jsonify(body), resp.status

    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return jsonify({"error": err_body}), e.code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
