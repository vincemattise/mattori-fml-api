"""
MATTORI FML API — Funda floorplan proxy for Shopify.
Hosted on Railway. Fetches FML data from Funda listings.
"""

import json
import os
import re
from typing import Optional

from flask import Flask, jsonify, request
from flask_cors import CORS
from curl_cffi import requests as cffi_requests

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
    return jsonify({"status": "ok", "service": "MATTORI FML API"})


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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
