# portal.py
# FastAPI-powered client portal with secure upload + view links.
import os, json, shutil, secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, Response, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import sqlite3

from run_report import (WORKSPACE, OUTPUTS_DIR, INCOMING_DIR, DB_PATH, ensure_dir,
                        db_init, db_connect, db_upsert_client, db_upsert_property,
                        db_insert_report, db_create_token, build_reports, now_iso)

ENV = dict(os.environ)
BASE_URL = ENV.get("PORTAL_EXTERNAL_BASE_URL", "http://localhost:8000")
TOKEN_TTL_HOURS = int(ENV.get("TOKEN_TTL_HOURS", "720"))
UPLOAD_TOKEN_TTL_HOURS = int(ENV.get("UPLOAD_TOKEN_TTL_HOURS", "48"))

app = FastAPI(title="Checkmyrental Client Portal", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Ensure workspace
for p in [WORKSPACE, OUTPUTS_DIR, INCOMING_DIR]:
    p.mkdir(parents=True, exist_ok=True)

def token_row(token: str):
    conn = db_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tokens WHERE token=? AND revoked=0", (token,))
        row = cur.fetchone()
        return row
    finally:
        conn.close()

def token_valid(row) -> bool:
    if not row: return False
    try:
        expires = datetime.fromisoformat(row["expires_at"].replace("Z",""))
        return datetime.utcnow() < expires
    except Exception:
        return False

@app.get("/health")
def health():
    return {"ok": True, "time": now_iso()}

UPLOAD_FORM_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Upload Inspection Photos</title>
<style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;background:#fafafa;color:#111}
.wrap{max-width:800px;margin:0 auto;padding:24px}
.card{background:#fff;border:1px solid #eee;border-radius:12px;padding:18px} h1{font-size:20px;margin:0 0 8px} .hint{color:#555;font-size:14px;margin-bottom:12px}
.row{margin:12px 0} input[type=file]{padding:12px;border:1px dashed #ccc;border-radius:10px;background:#fcfcfc;width:100%}
button{padding:10px 14px;border-radius:10px;border:1px solid #111;background:#111;color:#fff;cursor:pointer}
.badge{display:inline-block;padding:4px 8px;border-radius:999px;border:1px solid #ddd;background:#fff;margin-right:6px}
footer{padding:24px;color:#555;text-align:center}</style></head>
<body><div class="wrap"><div class="card">
<h1>Upload Inspection Photos</h1>
<div class="hint">Choose a ZIP of photos or select multiple images. When you submit, we'll generate the report automatically.</div>
<form method="post" enctype="multipart/form-data" action="/api/ingest?token={token}">
  <div class="row">
    <input type="file" name="files" multiple accept=".zip,image/*">
  </div>
  <div class="row">
    <button type="submit">Start Report</button>
  </div>
</form>
<div class="hint">Token: <span class="badge">{token}</span> Expires: <span class="badge">{expires}</span></div>
</div></div><footer>Checkmyrental</footer></body></html>"""

@app.get("/upload/{token}", response_class=HTMLResponse)
def upload_page(token: str):
    db_init()
    row = token_row(token)
    if not token_valid(row) or row["kind"] != "upload":
        raise HTTPException(status_code=403, detail="Invalid or expired upload link.")
    expires = row["expires_at"]
    return HTMLResponse(UPLOAD_FORM_HTML.format(token=token, expires=expires))

@app.post("/api/ingest", response_class=PlainTextResponse)
async def ingest(request: Request, token: Optional[str]=None, files: List[UploadFile]=File(...)):
    db_init()
    if token:
        row = token_row(token)
        if (not token_valid(row)) or row["kind"] != "upload":
            raise HTTPException(status_code=403, detail="Invalid or expired upload token.")
        payload = json.loads(row["payload_json"] or "{}")
        client_name = payload.get("client_name") or "Client"
        client_email = payload.get("client_email") or ""
        property_address = payload.get("property_address") or "Property"
    else:
        form = await request.form()
        client_name = form.get("client","Client")
        client_email = form.get("email","")
        property_address = form.get("property","Property")

    tmp_dir = ensure_dir(INCOMING_DIR / secrets.token_hex(6))
    zip_path = tmp_dir / "batch.zip"
    img_dir = ensure_dir(tmp_dir / "images")
    saw_zip = False
    for uf in files:
        fn = (uf.filename or "upload.bin")
        if fn.lower().endswith(".zip"):
            saw_zip = True
            with open(zip_path, "wb") as out:
                out.write(await uf.read())
        else:
            with open(img_dir / fn, "wb") as out:
                out.write(await uf.read())

    source = zip_path if saw_zip else img_dir

    try:
        from run_report import build_reports, register_with_portal
        artifacts = build_reports(source, client_name, property_address)
        reg = register_with_portal(artifacts, client_name, client_email, property_address, ttl_hours=TOKEN_TTL_HOURS)
        if token:
            conn = db_connect(); cur = conn.cursor()
            cur.execute("UPDATE tokens SET revoked=1 WHERE token=?", (token,)); conn.commit(); conn.close()
        return f"Report generated. Share link: {reg['share_url']}"
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/r/{token}", response_class=HTMLResponse)
def serve_report_index(token: str):
    db_init()
    row = token_row(token)
    if not token_valid(row) or row["kind"] != "view":
        raise HTTPException(status_code=403, detail="Invalid or expired view link.")
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT web_dir, pdf_path FROM reports WHERE id=?", (row["report_id"],))
    rep = cur.fetchone(); conn.close()
    if not rep: raise HTTPException(status_code=404, detail="Report not found.")
    web_dir = Path(rep["web_dir"])
    index_path = web_dir / "index.html"
    if not index_path.exists(): raise HTTPException(status_code=404, detail="Report index missing.")
    html = index_path.read_text(encoding="utf-8")
    # Ensure assets are served behind token
    base_tag = f'<base href="/asset/{token}/">'
    html = html.replace('</head>', base_tag + '</head>')
    # Floating PDF download button
    pdf_link_html = f'<div style="position:fixed;right:14px;bottom:14px"><a href="/api/pdf/{token}" style="text-decoration:none;padding:10px 12px;border-radius:10px;border:1px solid #111;background:#111;color:#fff">Download PDF</a></div>'
    html = html.replace("</body>", pdf_link_html + "</body>")
    return HTMLResponse(content=html)

@app.get("/asset/{token}/{path:path}")
def serve_asset(token: str, path: str):
    db_init()
    row = token_row(token)
    if not token_valid(row):
        raise HTTPException(status_code=403, detail="Invalid or expired token.")
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT web_dir FROM reports WHERE id=?", (row["report_id"],))
    rep = cur.fetchone(); conn.close()
    web_dir = Path(rep["web_dir"])
    file_path = (web_dir / path).resolve()
    if not str(file_path).startswith(str(web_dir.resolve())) or not file_path.exists():
        raise HTTPException(status_code=404, detail="Asset not found.")
    return FileResponse(str(file_path))

@app.get("/api/pdf/{token}")
def serve_pdf(token: str):
    db_init()
    row = token_row(token)
    if not token_valid(row) or row["kind"] != "view":
        raise HTTPException(status_code=403, detail="Invalid or expired view token.")
    conn = db_connect(); cur = conn.cursor()
    cur.execute("SELECT pdf_path FROM reports WHERE id=?", (row["report_id"],))
    rep = cur.fetchone(); conn.close()
    pdf_path = Path(rep["pdf_path"])
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF not found.")
    return FileResponse(str(pdf_path), media_type="application/pdf", filename="inspection_report.pdf")

# ---------------- Admin/CLI helpers ----------------
def create_upload_link(client_name: str, property_address: str, client_email: str="") -> str:
    db_init(); conn = db_connect()
    try:
        client_id = db_upsert_client(conn, client_name, client_email)
        prop_id = db_upsert_property(conn, client_id, property_address)
        payload = {"client_name": client_name, "client_email": client_email, "property_address": property_address}
        token = db_create_token(conn, kind="upload", ttl_hours=UPLOAD_TOKEN_TTL_HOURS, report_id=None, payload_json=json.dumps(payload))
        return f"{BASE_URL.rstrip('/')}/upload/{token}"
    finally:
        conn.close()

if __name__ == "__main__":
    # Simple CLI for admins to create upload links
    import argparse
    parser = argparse.ArgumentParser(description="Portal admin CLI")
    sub = parser.add_subparsers(dest="cmd")
    cu = sub.add_parser("create-upload-link")
    cu.add_argument("--client", required=True)
    cu.add_argument("--property", required=True)
    cu.add_argument("--email", default="")
    args = parser.parse_args()
    if args.cmd == "create-upload-link":
        print(create_upload_link(args.client, args.property, args.email))
    else:
        parser.print_help()