# Checkmyrental — Project Context for Claude Code

## 1) Product overview

I take property photos (ZIP or multiple images). The system automatically:

1. Analyzes the photos with GPT‑5–style vision.
2. Produces:
   - A **high‑quality PDF inspection report** (cover, branding, per‑photo notes).
   - A **mobile‑friendly interactive/digital report** (JSON-based, displayed via the portal).
3. Publishes the result to a **secure client portal** (desktop + mobile).

## 2) Current architecture (source of truth)

### Backend / processing
- **`run_report.py`**  
  - CLI: `python run_report.py --zip <photos.zip> [--address <label>] [--out <pdf>]`  
  - Unzips, orients images, calls `vision.describe_image(path)` in parallel, renders a branded PDF with ReportLab, writes a JSON summary, updates `output/reports_index.json`, and prints a `REPORT_ID=<uuid>` line used by the UI.  
  - Emits progress lines like `[3/12] IMG_0042.jpg | elapsed … ETA …` for the GUI to parse. :contentReference[oaicite:0]{index=0}

- **`vision.py`**  
  - Uses OpenAI’s Responses API client; downscales to `ANALYSIS_MAX_PX` **only for analysis** (PDF uses originals).  
  - Disk‑caches notes by hash; applies a defect‑focused second pass if the first pass looks too “safe.”  
  - Public entrypoint: **`describe_image(image_path: Path) -> str`** (returns structured notes text). :contentReference[oaicite:1]{index=1}

- **`.env`** (config)  
  - IMPORTANT keys (names only): `OPENAI_API_KEY`, `VISION_MODEL`, branding colors, font sizes, and performance toggles `JOB_CONCURRENCY`, `ANALYSIS_CONCURRENCY`, `ANALYSIS_MAX_PX`.  
  - DO NOT print secrets. Treat this file as sensitive. :contentReference[oaicite:2]{index=2}

- **Requirements**  
  - FastAPI/uvicorn, Pillow, ReportLab, OpenAI SDK, etc., are already pinned for local runs. :contentReference[oaicite:3]{index=3}

### Desktop frontend
- **`operator_ui.py`** (Tkinter drag‑and‑drop)  
  - Accepts ZIPs, launches `run_report.py`, parses the progress regex `[(\d+)/(\d+)]` and consumes `REPORT_ID=` lines to show links.  
  - Provides a log pane with clickable URLs. :contentReference[oaicite:4]{index=4}

### Portal API (Enhanced)
- **`api_main_enhanced.py`**  
  - FastAPI app exposing magic‑link auth, portal dashboard, signed URL serving for PDFs/JSON, pagination & search.  
  - Endpoints include `/auth/login`, `/auth/verify`, `/api/v2/portal/dashboard`, `/api/v2/portal/reports`, `/api/portal/signed/{resource_type}/{id}/{file_type}`. :contentReference[oaicite:5]{index=5}

- **`auth_utils.py`**  
  - Magic link generation/validation and **signed URL** generator for secure, time‑limited access to artifacts. :contentReference[oaicite:6]{index=6}

> Note: The portal expects each report record to have resolvable `pdf_path` and (optionally) `json_path`. Signed URLs are validated server‑side before serving files. :contentReference[oaicite:7]{index=7}

---

## 3) Desired end‑to‑end flow (what Claude should maintain)

1. **Ingest** a ZIP (or multiple images).  
2. **Analyze** each photo via `vision.describe_image(...)`. If the model returns weak output, a second pass intensifies defect finding (already implemented). :contentReference[oaicite:8]{index=8}  
3. **Generate**:
   - **PDF** (ReportLab): EXIF rotation fixed; LANCZOS scaling for quality; branded cover and per‑photo notes panel. :contentReference[oaicite:9]{index=9}  
   - **JSON** summary for the interactive/digital report (used by the portal app). :contentReference[oaicite:10]{index=10}
4. **Register/Publish** in the portal (create/update report record with `pdf_path`/`json_path`; portal serves these via time‑limited **signed URLs**). :contentReference[oaicite:11]{index=11}:contentReference[oaicite:12]{index=12}
5. **Surface to users**:
   - Desktop: Tk app shows progress and final links from `REPORT_ID` output. :contentReference[oaicite:13]{index=13}  
   - Web: Owner logs in via magic link; dashboard lists properties/reports with signed URLs to PDF/JSON. :contentReference[oaicite:14]{index=14}

---

## 4) Stable contracts (do **not** break without explicit approval)

- **Vision API:**  
  - Keep `describe_image(image_path: Path) -> str` public function. :contentReference[oaicite:15]{index=15}

- **Processor CLI & output:**  
  - `run_report.py --zip …` must work.  
  - Must print `REPORT_ID=<uuid>` once at the end (GUI depends on it). :contentReference[oaicite:16]{index=16}  
  - Must keep progress lines in the form `"[{i}/{n}] …"` (GUI parses with regex). :contentReference[oaicite:17]{index=17}

- **PDF quality guarantees:**  
  - Fix EXIF orientation; use LANCZOS for resizes; never analyze the full‑res image if `ANALYSIS_MAX_PX` is set (analysis only). :contentReference[oaicite:18]{index=18}:contentReference[oaicite:19]{index=19}

- **Portal contracts:**  
  - Do not remove/rename enhanced endpoints in `api_main_enhanced.py`. Keep signed‑URL validation flow intact. :contentReference[oaicite:20]{index=20}

- **Config:**  
  - Respect `.env` keys for branding and performance (names only per security). :contentReference[oaicite:21]{index=21}

---

## 5) Editing rules (“Notes for Claude”)

- Keep current project structure intact; prefer adding **small, surgical changes** over refactors.  
- Avoid invasive edits to existing modules unless strictly necessary.  
- If conflicts arise with existing routes or configs, propose the **smallest** compatibility‑preserving change, show the diff, then proceed.  
- When I ask to modify **`run_report.py`**, produce a **full file replacement** (I copy/paste the entire file).  
- Maintain Python 3.10+ compatibility and Black‑style formatting.

---

## 6) Performance & quality bar

- Concurrency via `.env`: `ANALYSIS_CONCURRENCY` (per‑ZIP image analysis workers), optional `JOB_CONCURRENCY` (if we add multi‑ZIP scheduling). :contentReference[oaicite:22]{index=22}  
- Only downscale for analysis; keep high‑quality images for PDF. :contentReference[oaicite:23]{index=23}  
- Don’t load all images into RAM at once for large ZIPs. Stream/decompress in batches. :contentReference[oaicite:24]{index=24}  
- GUI must continue to show **steady progress** and ETA; don’t change the progress line format. :contentReference[oaicite:25]{index=25}

---

## 7) Security & privacy

- Never log or echo secret values (API keys, tokens, signatures). `.env` contains secrets; **names may be referenced, values may not**. :contentReference[oaicite:26]{index=26}  
- Serve artifacts via signed, time‑limited URLs only (no direct disk paths in public responses). :contentReference[oaicite:27]{index=27}:contentReference[oaicite:28]{index=28}  
- Magic links must expire and be single‑use (already enforced in code paths). :contentReference[oaicite:29]{index=29}:contentReference[oaicite:30]{index=30}

---

## 8) Non‑goals (keep scope tight)

- No multi‑tenant admin UI or billing.  
- No external storage integration right now (design clean seams for S3/R2 later).  
- No heavy web frameworks for the interactive report; JSON + portal is sufficient for v1.

---

## 9) Definition of Done (DoD)

- ✅ `run_report.py` accepts a ZIP and produces:  
  - A branded, high‑quality PDF with per‑photo notes. :contentReference[oaicite:31]{index=31}  
  - A JSON summary suitable for the portal’s digital report view. :contentReference[oaicite:32]{index=32}  
- ✅ Progress and `REPORT_ID` are printed exactly as before; the GUI parses and displays them. :contentReference[oaicite:33]{index=33}  
- ✅ The portal lists the new report and serves **signed** PDF/JSON links that validate server‑side. :contentReference[oaicite:34]{index=34}:contentReference[oaicite:35]{index=35}  
- ✅ `.env` performance and branding knobs are respected; no secrets are printed. :contentReference[oaicite:36]{index=36}  
- ✅ No breaking changes to public function signatures or route paths listed above.

---

## 10) Handy task preface to keep using with Claude

> “Use `CONTEXT.md` as the project brief. Maintain the contracts in §4, security in §7, and DoD in §9. For `run_report.py`, return a full file replacement. Keep progress parsing compatible with `operator_ui.py`. Do not print secrets from `.env`.”

