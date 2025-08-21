# Write a hardened drop‑in replacement `frontend.py` that addresses the 5 issues
# the other model flagged: (1) os.startfile safety, (2) __file__ use when frozen,
# (3) same for worker path, (4) cleaner f-string escapes, (5) robust tkinterdnd2 import.
from pathlib import Path

frontend_py_fixed = r'''# frontend.py — Inspection Agent GUI (parallel ZIPs, hardened)
# Drop-in replacement; fixes:
# 1) Windows opener doesn't rely on os.startfile type-ignored call; adds graceful fallbacks.
# 2) Avoids brittle __file__ lookups; robust base-dir detection for frozen/packaged apps.
# 3) Same resolution applies to parallel workers.
# 4) Cleans escape sequences in f-strings (no embedded "\n" inside f-strings).
# 5) Adds safe import + fallback when tkinterdnd2 is missing (drag & drop disabled with guidance).
#
# Requires: tkinter, python-dotenv
# Optional: tkinterdnd2 (enables drag & drop)

import os
import sys
import threading
import subprocess
import queue
import time
import re
import json
import webbrowser
import shlex
import importlib.util
from pathlib import Path

# GUI
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Attempt to enable drag & drop if tkinterdnd2 is present
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
    BaseTk = TkinterDnD.Tk  # type: ignore[attr-defined]
    DND_AVAILABLE = True
except Exception:
    # Fallback: plain Tk; disable DND gracefully
    BaseTk = tk.Tk  # type: ignore[assignment]
    DND_FILES = None  # type: ignore[assignment]
    DND_AVAILABLE = False

# .env
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except Exception:
    pass

APP_TITLE = "Inspection Agent — Parallel Jobs"
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Parse lines like: [3/12] IMG_0042.jpg | elapsed 38s  ETA ~72s
PROGRESS_RE = re.compile(r"\\[(\\d+)\\s*/\\s*(\\d+)\\]")
START_RE = re.compile(r"Starting analysis of\\s+(\\d+)\\s+images\\b")
REPORT_ID_RE = re.compile(r"^REPORT_ID=(.+)$")

# Env knobs
def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default

JOB_CONCURRENCY = max(1, _int_env("JOB_CONCURRENCY", 1))
PORTAL_EXTERNAL_BASE_URL = os.getenv("PORTAL_EXTERNAL_BASE_URL", "http://localhost:8000").strip().rstrip("/")

def portal_url(path: str) -> str:
    """Join base portal URL with a path; accepts '/reports/...' or 'reports/...'. """
    path = path.strip()
    if not path.startswith("/"):
        path = "/" + path
    return f"{PORTAL_EXTERNAL_BASE_URL}{path}"

# --------- Robust path / invocation helpers ---------

def _get_base_dir() -> Path:
    """
    Resolve the directory where companion scripts live, even when frozen (PyInstaller).
    Preference order:
      1) sys._MEIPASS (PyInstaller extraction directory)
      2) Directory of the executable (when frozen)
      3) Directory of this file (normal run)
      4) Current working directory as last resort
    """
    # PyInstaller / frozen
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        # Fallback to the folder of the executable
        try:
            return Path(sys.executable).resolve().parent
        except Exception:
            pass
    # Normal script
    try:
        return Path(__file__).resolve().parent  # type: ignore[name-defined]
    except Exception:
        # Some packed environments may not set __file__
        return Path.cwd()

def _resolve_run_report_cmd(zip_path: Path) -> list[str] | None:
    """
    Best-effort resolution to a command that launches run_report for a given ZIP.
    Order:
    1) RUN_REPORT_CMD env override (e.g., "my-run-report --flag")
    2) Local 'run_report.py' next to this frontend (or CWD)
    3) Python module entry: 'python -m run_report'
    Returns a full argv including '--zip <path>' or None if not found.
    """
    # 1) Explicit override
    env_cmd = os.getenv("RUN_REPORT_CMD", "").strip()
    if env_cmd:
        try:
            parts = shlex.split(env_cmd)
            return parts + ["--zip", str(zip_path)]
        except Exception:
            pass

    # 2) Local script candidates
    base_dir = _get_base_dir()
    candidates = [
        base_dir / "run_report.py",
        Path.cwd() / "run_report.py",
    ]
    for cand in candidates:
        if cand.exists():
            return [sys.executable, str(cand), "--zip", str(zip_path)]

    # 3) Module form
    try:
        spec = importlib.util.find_spec("run_report")
        if spec is not None:
            return [sys.executable, "-m", "run_report", "--zip", str(zip_path)]
    except Exception:
        pass

    return None

# ---------- App ----------

class App(BaseTk):  # type: ignore[misc]
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1040x700")
        self.minsize(900, 560)

        # State
        self.zip_list: list[Path] = []
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.jobs_state = {}  # path -> dict(total:int|None, done:int, start:float|None, finished:bool, report_id:str|None)
        self._state_lock = threading.Lock()
        self._orchestrator = None  # background thread that manages all jobs

        # UI
        self._build_ui()
        self.after(120, self._pump_logs)  # log flusher
        self.after(250, self._poll_parallel_progress)  # progress aggregator

    # ----- UI construction -----
    def _build_ui(self):
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main, padding=8)
        left.pack(side="left", fill="y")

        right = ttk.Frame(main, padding=8)
        right.pack(side="right", fill="both", expand=True)

        # Left: controls + list
        btns = ttk.Frame(left)
        btns.pack(fill="x")
        ttk.Button(btns, text="Add ZIPs…", command=self.add_files).pack(side="left")
        ttk.Button(btns, text="Clear", command=self.clear_list).pack(side="left", padx=(6, 0))
        ttk.Button(btns, text="Open Output", command=self.open_output).pack(side="left", padx=(6, 0))

        run_frame = ttk.Frame(left)
        run_frame.pack(fill="x", pady=(12, 0))
        ttk.Button(run_frame, text=f"Run ({'Parallel' if JOB_CONCURRENCY>1 else 'Sequential'})", command=self.start).pack(side="left")
        ttk.Label(run_frame, text=f"JOB_CONCURRENCY={JOB_CONCURRENCY}").pack(side="left", padx=(10, 0))

        portal_frame = ttk.Frame(left)
        portal_frame.pack(fill="x", pady=(12, 8))
        ttk.Button(portal_frame, text="View Portal", command=self.view_portal).pack(side="left")
        ttk.Label(portal_frame, text=PORTAL_EXTERNAL_BASE_URL).pack(side="left", padx=(8, 0))

        self.listbox = tk.Listbox(left, width=42, height=26, selectmode="extended")
        self.listbox.pack(fill="y", pady=(8, 0))

        if DND_AVAILABLE:
            # Only register DND when the extension is present
            try:
                self.listbox.drop_target_register(DND_FILES)  # type: ignore[arg-type]
                self.listbox.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                # If anything goes wrong, silently disable DND
                pass
        else:
            # Provide a gentle hint that DND is disabled
            hint = tk.Label(left, text="Drag & drop disabled — install 'tkinterdnd2' to enable.", fg="orange")
            hint.pack(anchor="w", pady=(6, 0))

        # Right: log
        log_label = ttk.Label(right, text="Activity Log (double-click URLs to open)")
        log_label.pack(anchor="w")

        self.log = tk.Text(right, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)

        self.log.tag_configure("link", foreground="blue", underline=1)
        self.log.tag_bind("link", "<Double-Button-1>", self._on_link_click)
        self.log.tag_bind("link", "<Enter>", lambda e: self.log.config(cursor="hand2"))
        self.log.tag_bind("link", "<Leave>", lambda e: self.log.config(cursor=""))

        # Bottom: progress + ETA + status
        bar_frame = ttk.Frame(right)
        bar_frame.pack(fill="x", pady=(6, 0))
        self.progress = ttk.Progressbar(bar_frame, orient="horizontal", mode="indeterminate")
        self.progress.pack(fill="x", expand=True)
        self.eta_var = tk.StringVar(value="ETA: —")
        ttk.Label(right, textvariable=self.eta_var).pack(anchor="w", pady=(2, 0))

        self.status = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w")
        status_bar.pack(fill="x", side="bottom")

    # ----- File list management -----
    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select ZIP files",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
        )
        if not paths:
            return
        self._add_paths(paths)

    def _on_drop(self, event):
        raw = event.data
        items = self.splitlist(raw)
        self._add_paths(items)

    def _add_paths(self, items):
        added = 0
        for p in items:
            try:
                path = Path(str(p).strip("{}"))
                if path.suffix.lower() == ".zip" and path.exists():
                    if path not in self.zip_list:
                        self.zip_list.append(path)
                        self.listbox.insert("end", str(path))
                        added += 1
            except Exception:
                continue
        if added:
            self._log_line(f"Added {added} ZIP(s).")
        else:
            self._log_line("No new ZIPs added.")

    def clear_list(self):
        self.zip_list.clear()
        self.listbox.delete(0, "end")
        self._log_line("Cleared ZIP list.")

    # ----- Actions -----
    def start(self):
        if not self.zip_list:
            messagebox.showwarning("No files", "Add or drop at least one ZIP.")
            return

        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            messagebox.showerror("API key missing", "OPENAI_API_KEY not found in .env.")
            return

        # Reset progress
        self._clear_progress()
        mode = "parallel" if JOB_CONCURRENCY > 1 else "sequential"
        self._log_line(f"Starting {len(self.zip_list)} job(s) in {mode} mode…")
        self._set_status("Running…")

        # Orchestrator thread
        if self._orchestrator and self._orchestrator.is_alive():
            messagebox.showinfo("Already running", "Please wait for the current run to finish.")
            return

        self._orchestrator = threading.Thread(
            target=(self._run_all_parallel if JOB_CONCURRENCY > 1 else self._run_all_sequential),
            daemon=True,
        )
        self._orchestrator.start()

    def open_output(self):
        p = OUTPUT_DIR.resolve()
        try:
            if sys.platform == "win32":
                # Prefer os.startfile when available, otherwise fall back to explorer
                startfile = getattr(os, "startfile", None)
                if callable(startfile):
                    startfile(str(p))  # type: ignore[misc]
                else:
                    subprocess.run(["explorer", str(p)])
            elif sys.platform == "darwin":
                subprocess.run(["open", str(p)])
            else:
                subprocess.run(["xdg-open", str(p)])
        except Exception:
            # Last resort: show the absolute path
            messagebox.showinfo("Output Folder", f"Output folder: {p}")

    def view_portal(self):
        try:
            webbrowser.open(portal_url("/"))
        except Exception:
            pass

    # ----- Sequential path -----
    def _run_all_sequential(self):
        zips = list(self.zip_list)
        for i, z in enumerate(zips, start=1):
            self._run_one_zip_sequential(z, i, len(zips))

        self._set_status("Finished all jobs.")
        self._finish_progress()
        self._log_line("All jobs done.")
        self.open_output()

    def _run_one_zip_sequential(self, zip_path: Path, job_index: int, job_total: int):
        cmd = _resolve_run_report_cmd(zip_path)
        if not cmd:
            self._log_line("ERROR: Could not locate run_report. Set RUN_REPORT_CMD or place run_report.py next to frontend.py")
            return

        self._log_line("")  # (cleaner than embedding \n in f-string)
        self._log_line(f"=== [{job_index}/{job_total}] {zip_path.name} ===")
        self._start_indeterminate("Analyzing…")

        first_seen = None
        total_images = None
        report_id = None

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.rstrip()
                self._log_line(line)

                # REPORT_ID
                m_id = REPORT_ID_RE.match(line)
                if m_id:
                    report_id = m_id.group(1)
                    self._log_line(f"Interactive Report: {portal_url(f'/reports/{report_id}')}")

                # Progress
                m = PROGRESS_RE.search(line)
                if m:
                    idx_img = int(m.group(1))
                    total_images = int(m.group(2))
                    if first_seen is None:
                        first_seen = time.time()
                        self._start_determinate(total_images)
                    self._update_progress(idx_img, total_images, first_seen)

            rc = proc.wait()
            if rc == 0:
                if total_images is None:
                    self._finish_progress()
                    self._set_eta("Done")
                else:
                    self._set_eta(f"Done  •  {total_images}/{total_images}")
                self._log_line(f"✓ Done: {zip_path.name}")
                if report_id:
                    self._log_line(f"Interactive Report: {portal_url(f'/reports/{report_id}')}")
                    self._log_line("(Click the link to open in browser)")
            else:
                self._finish_progress()
                self._set_eta("Failed")
                self._log_line(f"✗ Failed ({rc}): {zip_path.name}")

        except Exception as e:
            self._finish_progress()
            self._set_eta("Error")
            self._log_line(f"ERROR running {zip_path.name}: {e}")

    # ----- Parallel path -----
    def _run_all_parallel(self):
        # Reset shared job state
        with self._state_lock:
            self.jobs_state = {p: {"total": None, "done": 0, "start": None, "finished": False, "report_id": None}
                               for p in self.zip_list}
        self._start_indeterminate("Analyzing (parallel)…")

        # Launch workers with a bounded pool
        sem = threading.Semaphore(JOB_CONCURRENCY)
        workers = []

        def launch(zip_path: Path):
            with sem:
                self._run_one_zip_worker(zip_path)

        for p in self.zip_list:
            t = threading.Thread(target=launch, args=(p,), daemon=True)
            workers.append(t)
            t.start()

        for t in workers:
            t.join()

        self._set_status("Finished all jobs.")
        self._finish_progress()
        totals = [st for st in self.jobs_state.values()]
        global_total = sum((st.get("total") or 0) for st in totals)
        global_done = sum(st.get("done", 0) for st in totals)
        self._log_line(f"All jobs done. ({global_done}/{global_total} images processed)")
        self.open_output()

    def _run_one_zip_worker(self, zip_path: Path):
        cmd = _resolve_run_report_cmd(zip_path)
        if not cmd:
            self._log_line("ERROR: Could not locate run_report. Set RUN_REPORT_CMD or place run_report.py next to frontend.py")
            with self._state_lock:
                st = self.jobs_state.get(zip_path, {})
                st["finished"] = True
                self.jobs_state[zip_path] = st
            return

        self._log_line("")
        self._log_line(f"=== {zip_path.name} ===")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None

            job_started = False
            for raw in proc.stdout:
                line = raw.rstrip()
                # Prefix lines by ZIP for clarity when parallel
                self._log_line(f"[{zip_path.name}] {line}")

                # Total images advertisement
                m0 = START_RE.search(line)
                if m0:
                    total = int(m0.group(1))
                    with self._state_lock:
                        state = self.jobs_state.get(zip_path, {})
                        state["total"] = total
                        if not job_started:
                            state["start"] = time.time()
                            job_started = True
                        self.jobs_state[zip_path] = state

                # Progress updates
                m = PROGRESS_RE.search(line)
                if m:
                    done = int(m.group(1))
                    total = int(m.group(2))
                    with self._state_lock:
                        state = self.jobs_state.get(zip_path, {})
                        state["total"] = state.get("total") or total
                        if not job_started:
                            state["start"] = time.time()
                            job_started = True
                        state["done"] = done
                        self.jobs_state[zip_path] = state

                # REPORT_ID for portal
                m_id = REPORT_ID_RE.match(line)
                if m_id:
                    rid = m_id.group(1)
                    with self._state_lock:
                        state = self.jobs_state.get(zip_path, {})
                        state["report_id"] = rid
                        self.jobs_state[zip_path] = state
                    self._log_line(f"[{zip_path.name}] Interactive Report: {portal_url(f'/reports/{rid}')}")

            rc = proc.wait()
            with self._state_lock:
                st = self.jobs_state.get(zip_path, {})
                st["finished"] = True
                self.jobs_state[zip_path] = st

            if rc == 0:
                self._log_line(f"✓ Done: {zip_path.name}")
            else:
                self._log_line(f"✗ Failed ({rc}): {zip_path.name}")

        except Exception as e:
            self._log_line(f"ERROR running {zip_path.name}: {e}")
            with self._state_lock:
                st = self.jobs_state.get(zip_path, {})
                st["finished"] = True
                self.jobs_state[zip_path] = st

    # ----- Progress helpers -----
    def _clear_progress(self):
        def _do():
            self.progress.stop()
            self.progress.configure(mode="indeterminate", maximum=100, value=0)
            self.eta_var.set("ETA: —")
        self.after(0, _do)

    def _start_indeterminate(self, status_text="Working…"):
        def _do():
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
            self.status.set(status_text)
            self.eta_var.set("ETA: —")
        self.after(0, _do)

    def _start_determinate(self, total_images: int):
        def _do():
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=total_images, value=0)
        self.after(0, _do)

    def _update_progress(self, idx_img: int, total_images: int, first_seen_time: float):
        def _do():
            if self.progress["mode"] != "determinate":
                self._start_determinate(total_images)
            self.progress["value"] = idx_img
            elapsed = time.time() - first_seen_time
            avg = elapsed / max(1, idx_img)
            remaining = int(avg * (total_images - idx_img))
            self.eta_var.set(f"ETA: ~{remaining}s  •  {idx_img}/{total_images}")
        self.after(0, _do)

    def _set_eta(self, text: str):
        self.after(0, lambda: self.eta_var.set(text))

    def _finish_progress(self):
        def _do():
            self.progress.stop()
        self.after(0, _do)

    def _set_status(self, text: str):
        self.after(0, lambda: self.status.set(text))

    # ----- Aggregator for parallel mode -----
    def _poll_parallel_progress(self):
        """Every 250 ms, compute a global progress/ETA across parallel jobs and update the bar."""
        try:
            with self._state_lock:
                states = list(self.jobs_state.values())
            if states:
                totals_known = [s["total"] for s in states if s.get("total")]
                global_total = sum(totals_known) if totals_known else 0
                global_done = sum(s.get("done", 0) for s in states)
                running = [s for s in states if s.get("start") and not s.get("finished")]
                now = time.time()

                if global_total > 0:
                    # determinate
                    def _do():
                        self.progress.stop()
                        self.progress.configure(mode="determinate", maximum=global_total, value=global_done)
                    self.after(0, _do)

                    # ETA: weighted avg sec/image
                    den = sum(s.get("done", 0) for s in states if s.get("start"))
                    if den > 0:
                        num = sum((now - s["start"]) for s in states if s.get("start"))
                        avg = num / max(1, den)
                        remaining = int(avg * max(0, global_total - global_done))
                        self._set_eta(f"ETA: ~{remaining}s  •  {global_done}/{global_total}  •  {len(running)} active")
                    else:
                        self._set_eta(f"{global_done}/{global_total}")
                # else: remain indeterminate until totals are known

                # When all jobs finished, show Done
                if states and all(s.get("finished") for s in states) and global_total > 0:
                    self._set_eta(f"Done  •  {global_total}/{global_total}")
        except Exception:
            # Best-effort; keep UI responsive even if something goes wrong
            pass
        finally:
            self.after(250, self._poll_parallel_progress)

    # ----- Logging -----
    def _log_line(self, text: str):
        self.log_queue.put(text)

    def _pump_logs(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.log.configure(state="normal")

                # Turn URLs into clickable links
                parts = self._linkify(line)
                for seg_text, tag in parts:
                    if tag == "link":
                        start_idx = self.log.index("end-1c")
                        self.log.insert("end", seg_text, ("link", f"url:{seg_text}"))
                    else:
                        self.log.insert("end", seg_text)

                self.log.insert("end", "\\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._pump_logs)

    def _linkify(self, text: str):
        """Return [(segment, tag)] where tag is 'link' or None; naive URL detection."""
        out = []
        url_re = re.compile(r"(https?://\\S+)")
        last = 0
        for m in url_re.finditer(text):
            if m.start() > last:
                out.append((text[last:m.start()], None))
            out.append((m.group(1), "link"))
            last = m.end()
        if last < len(text):
            out.append((text[last:], None))
        return out

    def _on_link_click(self, event):
        tags = self.log.tag_names("current")
        for tag in tags:
            if tag.startswith("url:"):
                url = tag[4:]
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
                break

if __name__ == "__main__":
    app = App()
    app.mainloop()
'''

# Execute the actual app code directly
exec(frontend_py_fixed)
