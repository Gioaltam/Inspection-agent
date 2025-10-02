# operator_ui.py — Inspection Agent GUI (parallel ZIPs, hardened)
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
import requests
from pathlib import Path
import ctypes
import platform
import math
import zipfile
import atexit

# Enable DPI awareness for Windows (sharper text)
if platform.system() == 'Windows':
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
    except:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # System DPI aware
        except:
            pass

# GUI
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from tkinter import font as tkFont

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

# ============ BRANDING CONFIGURATION ============
COMPANY_NAME = "CheckMyRental"
APP_TITLE = "Inspector Portal"
APP_VERSION = "v2.0 Professional"
APP_TAGLINE = "Professional Property Inspection Reports"

# CheckMyRental Brand Colors (Modern Dark Mode with 3D Effects)
BRAND_PRIMARY = "#e74c3c"  # CheckMyRental Red
BRAND_PRIMARY_HOVER = "#c0392b"  # Darker red for hover
BRAND_PRIMARY_LIGHT = "#ff6b6b"  # Lighter red for gradients
BRAND_SECONDARY = "#3b82f6"  # Accent Blue
BRAND_SECONDARY_HOVER = "#2563eb"  # Darker blue for hover
BRAND_SECONDARY_LIGHT = "#60a5fa"  # Lighter blue for gradients
BRAND_SUCCESS = "#10b981"  # Success Green
BRAND_SUCCESS_LIGHT = "#34d399"  # Light green for gradients
BRAND_ERROR = "#dc2626"  # Error Red
BRAND_WARNING = "#ff9500"  # Warning Orange (vibrant, pure orange)

# Modern ultra-dark theme with depth layers
BRAND_BG = "#0a0e14"  # Ultra dark background
BRAND_BG_GRADIENT = "#0d1117"  # Gradient end
BRAND_SURFACE = "#161b22"  # Card background
BRAND_SURFACE_LIGHT = "#21262d"  # Elevated surface
BRAND_SURFACE_HOVER = "#30363d"  # Hover state
BRAND_SURFACE_ELEVATED = "#2d333b"  # More elevated surfaces
BRAND_TEXT = "#f0f6fc"  # Bright white text
BRAND_TEXT_SECONDARY = "#8b949e"  # Secondary text
BRAND_TEXT_DIM = "#6e7681"  # Dimmed text
BRAND_BORDER = "#30363d"  # Subtle border
BRAND_BORDER_LIGHT = "#21262d"  # Even subtler border
BRAND_SHADOW = "#000000"  # Shadow color
BRAND_SHADOW_LIGHT = "#1a1a1a"  # Light shadow for transparency simulation
BRAND_GLOW = "#ff9999"  # Red glow effect (light red instead of transparency)

OUTPUT_DIR = Path("workspace/outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Settings file path
SETTINGS_FILE = Path.home() / ".checkmyrental_inspector.json"

# Parse lines like: [3/12] IMG_0042.jpg | elapsed 38s  ETA ~72s
PROGRESS_RE = re.compile(r"\\[(\\d+)\\s*/\\s*(\\d+)\\]")
START_RE = re.compile(r"Starting analysis of\\s+(\\d+)\\s+images\\b")
REPORT_ID_RE = re.compile(r"^REPORT_ID=(.+)$")
OUTPUT_DIR_RE = re.compile(r"^OUTPUT_DIR=(.+)$")

# Env knobs
def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default

JOB_CONCURRENCY = max(1, _int_env("JOB_CONCURRENCY", 1))
ANALYSIS_CONCURRENCY = max(1, _int_env("ANALYSIS_CONCURRENCY", 3))
PORTAL_EXTERNAL_BASE_URL = os.getenv("PORTAL_EXTERNAL_BASE_URL", "http://localhost:5000").strip().rstrip("/")

PLACEHOLDER_OWNER = "Select owner..."

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

def _resolve_run_report_cmd(zip_path: Path, client_name: str = "", property_address: str = "", owner_name: str = "", owner_id: str = "", gallery: str = "") -> list[str] | None:
    """
    Best-effort resolution to a command that launches run_report for a given ZIP.
    Order:
    1) RUN_REPORT_CMD env override (e.g., "my-run-report --flag")
    2) Local 'run_report.py' next to this frontend (or CWD)
    3) Python module entry: 'python -m run_report'
    Returns a full argv including '--zip <path>', '--client', '--property' or None if not found.
    """
    # Always use ZIP filename as property address (ignoring any passed parameter)
    property_address = zip_path.stem.replace('_', ' ')
    
    # Build the command arguments
    args = ["--zip", str(zip_path), "--register"]  # Add --register for portal upload
    
    # Use owner_name as client if provided, otherwise use inspector name
    effective_client = owner_name if owner_name else client_name
    if effective_client:
        args.extend(["--client", effective_client])
    
    if property_address:
        args.extend(["--property", property_address])
    
    # Add owner ID if provided
    if owner_id:
        args.extend(["--owner-id", owner_id])
    
    # Add gallery if provided
    if gallery:
        args.extend(["--gallery", gallery])
    
    # 1) Explicit override
    env_cmd = os.getenv("RUN_REPORT_CMD", "").strip()
    if env_cmd:
        try:
            parts = shlex.split(env_cmd)
            return parts + args
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
            return [sys.executable, str(cand)] + args

    # 3) Module form
    try:
        spec = importlib.util.find_spec("run_report")
        if spec is not None:
            return [sys.executable, "-m", "run_report"] + args
    except Exception:
        pass

    return None

# ---------- App ----------

class App(BaseTk):  # type: ignore[misc]
    def __init__(self):
        super().__init__()
        self.title(f"{COMPANY_NAME} - {APP_TITLE} {APP_VERSION}")
        
        # Configure default font for better clarity
        default_font = tkFont.nametofont("TkDefaultFont")
        default_font.configure(family="Segoe UI", size=10)
        self.option_add("*Font", default_font)
        
        # Get screen dimensions to size window appropriately
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Use 90% of screen height, 85% of width to maximize vertical space
        width = min(int(screen_width * 0.85), 1400)
        height = min(int(screen_height * 0.90), 950)  # Increased max height
        
        # Ensure minimum size for usability
        width = max(width, 1000)
        height = max(height, 750)  # Increased minimum height
        
        # Center window on screen with small top margin
        x = (screen_width // 2) - (width // 2)
        y = max(10, (screen_height // 2) - (height // 2) - 30)  # Small top margin
        
        # Set geometry and minimum size
        self.geometry(f'{width}x{height}+{x}+{y}')
        self.minsize(1100, 650)  # Adjusted minimum size
        
        # Allow window to be maximized
        self.state('normal')  # Start in normal state
        
        # If window is still too small for screen, maximize it
        if height < 750 or screen_height < 900:
            self.after(100, lambda: self.state('zoomed'))  # Maximize on Windows
        
        # Configure window background
        self.configure(bg=BRAND_BG)
        
        # Setup custom styles
        self.setup_styles()

        # State
        self.zip_list: list[Path] = []
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.jobs_state = {}  # path -> dict(total:int|None, done:int, start:float|None, finished:bool, report_id:str|None)
        self.job_rows: dict[Path, str] = {}  # Maps zip_path to treeview row iid
        self.proc_map: dict[Path, subprocess.Popen] = {}  # Maps zip_path to running process
        self._state_lock = threading.Lock()
        self._orchestrator = None  # background thread that manages all jobs
        self.pause_event = threading.Event()
        self.pause_event.set()  # Start unpaused
        self.cancel_flags: dict[Path, bool] = {}  # Track which jobs are canceled
        self.owner_id_map: dict[str, str] = {}
        self.owner_display_by_id: dict[str, str] = {}
        self.owner_details: dict[str, dict] = {}
        self.pending_owner_id: str = ""
        self.pending_owner_display: str = ""
        self.paused = False  # Track pause state for UI

        # UI
        self._build_ui()
        self.after(120, self._pump_logs)  # log flusher
        self.after(250, self._poll_parallel_progress)  # progress aggregator
        
        # Load and apply settings after UI is built
        self.load_and_apply_settings()
        
        # Register cleanup on window close
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        atexit.register(self.save_settings)
    
    def setup_styles(self):
        """Configure ttk styles for 3D dark mode appearance with shadows"""
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Configure 3D button styles with shadows
        self.style.configure(
            'Primary.TButton',
            background=BRAND_PRIMARY,
            foreground='white',
            borderwidth=2,
            bordercolor=BRAND_PRIMARY_LIGHT,
            darkcolor=BRAND_PRIMARY_HOVER,
            lightcolor=BRAND_PRIMARY_LIGHT,
            focuscolor='none',
            font=('Segoe UI', 11, 'bold'),
            relief='raised',
            padding=(12, 8)
        )
        self.style.map('Primary.TButton',
            background=[('active', BRAND_PRIMARY_HOVER), ('pressed', BRAND_PRIMARY_HOVER)],
            relief=[('pressed', 'sunken'), ('active', 'raised')]
        )
        
        self.style.configure(
            'Secondary.TButton',
            background=BRAND_SURFACE_ELEVATED,
            foreground=BRAND_TEXT,
            borderwidth=2,
            bordercolor=BRAND_BORDER,
            darkcolor=BRAND_SURFACE,
            lightcolor=BRAND_SURFACE_HOVER,
            focuscolor='none',
            font=('Segoe UI', 10, 'normal'),
            relief='raised',
            padding=(10, 6)
        )
        self.style.map('Secondary.TButton',
            background=[('active', BRAND_SURFACE_HOVER), ('pressed', BRAND_SURFACE)],
            relief=[('pressed', 'sunken'), ('active', 'raised')]
        )
        
        self.style.configure(
            'Success.TButton',
            background=BRAND_SUCCESS,
            foreground='white',
            borderwidth=2,
            bordercolor=BRAND_SUCCESS_LIGHT,
            darkcolor='#0d9668',
            lightcolor=BRAND_SUCCESS_LIGHT,
            focuscolor='none',
            font=('Segoe UI', 12, 'bold'),
            relief='raised',
            padding=(14, 10)
        )
        self.style.map('Success.TButton',
            background=[('active', '#0d9668'), ('pressed', '#0a7e5c')],
            relief=[('pressed', 'sunken'), ('active', 'raised')]
        )
        
        # Configure 3D frame styles with depth
        self.style.configure('Brand.TFrame', background=BRAND_BG)
        self.style.configure('Elevated.TFrame', background=BRAND_SURFACE, relief='raised', borderwidth=2)
        self.style.configure('Brand.TLabelframe', 
                           background=BRAND_SURFACE,
                           foreground=BRAND_TEXT,
                           bordercolor=BRAND_BORDER,
                           relief='raised',
                           borderwidth=2)
        self.style.configure('Brand.TLabelframe.Label', 
                           background=BRAND_SURFACE,
                           foreground=BRAND_PRIMARY_LIGHT,
                           font=('Segoe UI', 11, 'bold'))
        
        # Configure label styles
        self.style.configure('Brand.TLabel',
                           background=BRAND_BG,
                           foreground=BRAND_TEXT)
        self.style.configure('Heading.TLabel',
                           background=BRAND_BG,
                           foreground=BRAND_TEXT,
                           font=('Segoe UI', 12, 'bold'))
        
        # Configure enhanced progress bar with gradient effect
        self.style.configure('Enhanced.Horizontal.TProgressbar',
                           background=BRAND_PRIMARY,
                           troughcolor=BRAND_SURFACE,
                           bordercolor=BRAND_BORDER,
                           lightcolor=BRAND_PRIMARY_LIGHT,
                           darkcolor=BRAND_PRIMARY_HOVER,
                           borderwidth=2,
                           relief='raised')
        
        # Jobs table (Treeview) — larger rows + padded headers
        self.style.configure(
            'Jobs.Treeview',
            background=BRAND_SURFACE,
            fieldbackground=BRAND_SURFACE,
            foreground=BRAND_TEXT,
            bordercolor=BRAND_BORDER,
            rowheight=28,
        )
        self.style.map('Jobs.Treeview', background=[('selected', BRAND_SURFACE_HOVER)])
        
        self.style.configure(
            'Jobs.Treeview.Heading',
            background=BRAND_SURFACE_ELEVATED,
            foreground=BRAND_TEXT,
            bordercolor=BRAND_BORDER,
            font=('Segoe UI', 10, 'bold'),
            padding=(8, 6),
        )

    # ----- UI construction -----
    def _build_ui(self):
        # Create branded header
        self._create_header()
        
        # Main container with reduced padding
        main = ttk.Frame(self, style='Brand.TFrame')
        main.pack(fill="both", expand=True, padx=2, pady=1)

        # Left panel with 3D elevated card effect - increased width
        left_shadow = tk.Frame(main, bg=BRAND_SHADOW, width=750)
        left_shadow.pack(side="left", fill="both", expand=True, padx=(1, 2), pady=1)
        left_shadow.pack_propagate(False)  # Maintain fixed width
        
        left_container = ttk.LabelFrame(left_shadow, text="🏠 INSPECTION CONTROL", padding=8, style='Brand.TLabelframe')
        left_container.pack(fill="both", expand=True, padx=(0, 1), pady=(0, 1))
        left = ttk.Frame(left_container, style='Brand.TFrame')
        left.pack(fill="both", expand=True)

        # Right panel with 3D elevated card effect - reduced size
        right_shadow = tk.Frame(main, bg=BRAND_SHADOW, width=280)
        right_shadow.pack(side="right", fill="y", padx=(0, 1), pady=1)
        right_shadow.pack_propagate(False)  # Maintain fixed width
        
        right_container = ttk.LabelFrame(right_shadow, text="📋 ACTIVITY LOG", padding=6, style='Brand.TLabelframe')
        right_container.pack(fill="both", expand=True, padx=(0, 1), pady=(0, 1))
        right = ttk.Frame(right_container, style='Brand.TFrame')
        right.pack(fill="both", expand=True)

        # Modern button group with hover effects
        btns = tk.Frame(left, bg=BRAND_SURFACE)
        btns.pack(fill="x", pady=(0, 5))
        
        # Helper function to create 3D buttons with depth and animations
        def create_3d_button(parent, text, command, primary=False, pack_side="left", padx=(0, 0)):
            # Create button frame for shadow effect
            btn_frame = tk.Frame(parent, bg=BRAND_SURFACE, bd=0)
            btn_frame.pack(side=pack_side, padx=padx, pady=2)
            
            # Shadow layer
            shadow = tk.Frame(btn_frame, bg=BRAND_SHADOW, height=42, width=120)
            shadow.place(x=3, y=3)
            
            # Main button with gradient effect
            bg = BRAND_PRIMARY if primary else BRAND_SURFACE_ELEVATED
            hover = BRAND_PRIMARY_HOVER if primary else BRAND_SURFACE_HOVER
            light = BRAND_PRIMARY_LIGHT if primary else BRAND_SURFACE_HOVER
            fg = "white" if primary else BRAND_TEXT
            
            btn = tk.Button(btn_frame, text=text, command=command,
                          bg=bg, fg=fg, font=('Segoe UI', 11, 'bold' if primary else 'normal'),
                          bd=2, relief='raised', padx=20, pady=10,
                          cursor="hand2", activebackground=hover,
                          highlightbackground=light, highlightthickness=1)
            
            # Enhanced hover effects with animations
            def on_enter(e):
                btn.config(bg=hover, relief='ridge')
                shadow.place(x=4, y=4)  # Move shadow for depth
                if primary:
                    btn_frame.config(bg=BRAND_GLOW)  # Add glow effect
            
            def on_leave(e):
                btn.config(bg=bg, relief='raised')
                shadow.place(x=3, y=3)  # Reset shadow
                btn_frame.config(bg=BRAND_SURFACE)
            
            def on_press(e):
                btn.config(relief='sunken')
                shadow.place(x=1, y=1)  # Minimize shadow on press
            
            def on_release(e):
                btn.config(relief='raised')
                shadow.place(x=3, y=3)
            
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            btn.bind("<ButtonPress-1>", on_press)
            btn.bind("<ButtonRelease-1>", on_release)
            btn.pack()
            
            return btn_frame
        
        create_3d_button(btns, "📁  Add Files", self.add_files, primary=True)
        create_3d_button(btns, "🗑️  Clear", self.clear_list, padx=(12, 0))
        create_3d_button(btns, "📂  Reports", self.open_output, padx=(12, 0))

        # Enhanced run button with glow effect
        run_frame = ttk.Frame(left, style='Brand.TFrame')
        run_frame.pack(fill="x", pady=(5, 0))
        
        # Create glowing success button with light green shadow
        run_shadow = tk.Frame(run_frame, bg="#1a3d2e", height=50, width=200)
        run_shadow.place(x=3, y=3)
        
        ttk.Button(run_frame, text="✨ GENERATE REPORTS", command=self.start, style='Success.TButton').pack(side="left")
        
        # Add pause/resume button
        self.pause_btn = ttk.Button(run_frame, text="⏸️ PAUSE", command=self.toggle_pause, style='Secondary.TButton')
        self.pause_btn.pack(side="left", padx=(10, 0))
        self.pause_btn.config(state="disabled")  # Disabled until jobs start
        
        self.speed_label = tk.Label(run_frame, text=f"⚡ Fast Processing ({JOB_CONCURRENCY}×{ANALYSIS_CONCURRENCY})", 
                             font=('Segoe UI', 10, 'italic'), fg=BRAND_SUCCESS_LIGHT, bg=BRAND_BG)
        self.speed_label.pack(side="left", padx=(12, 0))

        # Property details with elevated 3D card
        details_shadow = tk.Frame(left, bg=BRAND_SHADOW)
        details_shadow.pack(fill="x", pady=(5, 2))
        
        client_frame = ttk.LabelFrame(details_shadow, text="🔍 INSPECTION DETAILS", padding=15, style='Brand.TLabelframe')
        client_frame.pack(fill="x", padx=(0, 3), pady=(0, 3))
        
        # Owner/Customer selection
        ttk.Label(client_frame, text="Select Owner Portal:", font=('Segoe UI', 13, 'bold'), style='Brand.TLabel').pack(anchor="w", pady=(0, 4))
        
        owner_selection_frame = ttk.Frame(client_frame, style='Brand.TFrame')
        owner_selection_frame.pack(fill="x", pady=(5, 8))
        
        self.owner_var = tk.StringVar()
        self.owner_combo = ttk.Combobox(owner_selection_frame, textvariable=self.owner_var, width=35, 
                                       font=('Segoe UI', 12), state='readonly', values=(PLACEHOLDER_OWNER,))
        self.owner_combo.pack(side="left", fill="x", expand=True)
        self.owner_combo.current(0)
        self.owner_combo.bind('<<ComboboxSelected>>', self._on_owner_selected)
        
        # Refresh button to fetch owners with CheckMyRental styling
        self.refresh_btn = ttk.Button(owner_selection_frame, text="🔄", width=3,
                                     command=self.refresh_owners, style='Secondary.TButton')
        self.refresh_btn.pack(side="left", padx=(5, 0))
        
        # Owner ID is now automatically set from the paid owners dropdown
        # No manual entry needed - routing is automatic for paid customers
        self.owner_id_var = tk.StringVar()  # Still needed internally for routing

        # Show helpful info about automatic routing
        auto_route_label = ttk.Label(client_frame, text="✅ Dashboard routing is automatic for paid customers",
                                    font=('Segoe UI', 11, 'italic'), foreground=BRAND_SUCCESS_LIGHT,
                                    style='Brand.TLabel')
        auto_route_label.pack(anchor="w", pady=(10, 4))
        
        # Property address info (automatically extracted from filename)
        ttk.Label(client_frame, text="Property Address: Automatically extracted from ZIP filename", 
                 font=('Segoe UI', 11, 'italic'), foreground=BRAND_TEXT_SECONDARY,
                 style='Brand.TLabel').pack(anchor="w", pady=(5, 12))
        
        # Client name for records (inspector/employee name)
        ttk.Label(client_frame, text="Inspector Name (optional):", font=('Segoe UI', 13, 'bold'), style='Brand.TLabel').pack(anchor="w", pady=(5, 4))
        self.client_name_var = tk.StringVar()
        self.client_name_entry = ttk.Entry(client_frame, textvariable=self.client_name_var, width=40, font=('Segoe UI', 12))
        self.client_name_entry.pack(fill="x", pady=(4, 0))
        
        # Advanced settings (concurrency controls)
        advanced_frame = ttk.LabelFrame(client_frame, text="⚙️ Advanced Settings (Optional)", style='Brand.TLabelframe')
        advanced_frame.pack(fill="x", pady=(5, 0))
        
        # Job concurrency spinner
        job_frame = ttk.Frame(advanced_frame, style='Brand.TFrame')
        job_frame.pack(fill="x", pady=(3, 3))
        
        ttk.Label(job_frame, text="Parallel Jobs:", font=('Segoe UI', 9), style='Brand.TLabel').pack(side="left")
        self.job_concurrency_var = tk.IntVar(value=JOB_CONCURRENCY)
        self.job_concurrency_spin = ttk.Spinbox(job_frame, from_=1, to=10, textvariable=self.job_concurrency_var, 
                                               width=5, font=('Segoe UI', 9), command=self.update_concurrency)
        self.job_concurrency_spin.pack(side="left", padx=(5, 10))
        
        # Analysis concurrency spinner
        ttk.Label(job_frame, text="Images per Job:", font=('Segoe UI', 9), style='Brand.TLabel').pack(side="left")
        self.analysis_concurrency_var = tk.IntVar(value=ANALYSIS_CONCURRENCY)
        self.analysis_concurrency_spin = ttk.Spinbox(job_frame, from_=1, to=10, textvariable=self.analysis_concurrency_var,
                                                    width=5, font=('Segoe UI', 9), command=self.update_concurrency)
        self.analysis_concurrency_spin.pack(side="left", padx=(5, 0))
        
        # Auto-fetch owners on startup and then every 30 seconds
        self.after(500, self.refresh_owners)
        self.after(30000, self._auto_refresh_owners)  # Start auto-refresh timer
        
        # Portal button with improved styling matching landing page
        portal_frame = ttk.Frame(left, style='Brand.TFrame')
        portal_frame.pack(fill="x", pady=(5, 4))
        
        # Create custom portal button with better lighting effect
        portal_btn_frame = tk.Frame(portal_frame, bg=BRAND_BG, bd=0)
        portal_btn_frame.pack(side="left")
        
        # Shadow layer for depth
        portal_shadow = tk.Frame(portal_btn_frame, bg=BRAND_SHADOW, height=44, width=180)
        portal_shadow.place(x=2, y=2)
        
        # Main portal button with gradient-like effect
        portal_btn = tk.Button(portal_btn_frame, text="🌐  Owner Portal", 
                             command=self.view_portal,
                             bg=BRAND_PRIMARY, fg="white", 
                             font=('Segoe UI', 11, 'bold'),
                             bd=1, relief='raised', padx=22, pady=10,
                             cursor="hand2", activebackground=BRAND_PRIMARY_HOVER,
                             highlightbackground=BRAND_PRIMARY_LIGHT, highlightthickness=1)
        
        # Improved hover effects without bouncing light
        def on_enter_portal(e):
            portal_btn.config(bg=BRAND_PRIMARY_HOVER, relief='ridge')
            portal_shadow.place(x=3, y=3)
            portal_btn_frame.config(bg=BRAND_GLOW)  # Use predefined glow color
        
        def on_leave_portal(e):
            portal_btn.config(bg=BRAND_PRIMARY, relief='raised')
            portal_shadow.place(x=2, y=2)
            portal_btn_frame.config(bg=BRAND_BG)
        
        def on_press_portal(e):
            portal_btn.config(relief='sunken')
            portal_shadow.place(x=1, y=1)
        
        def on_release_portal(e):
            portal_btn.config(relief='raised')
            portal_shadow.place(x=2, y=2)
        
        portal_btn.bind("<Enter>", on_enter_portal)
        portal_btn.bind("<Leave>", on_leave_portal)
        portal_btn.bind("<ButtonPress-1>", on_press_portal)
        portal_btn.bind("<ButtonRelease-1>", on_release_portal)
        portal_btn.pack()
        
        portal_label = tk.Label(portal_frame, text="Access CheckMyRental Dashboard", 
                              font=('Segoe UI', 10), fg=BRAND_PRIMARY_LIGHT, bg=BRAND_BG)
        portal_label.pack(side="left", padx=(12, 0))

        # Jobs table with 3D inset effect
        list_label = ttk.Label(left, text="📸 Inspection Jobs:", style='Heading.TLabel')
        list_label.pack(anchor="w", pady=(3, 1))
        
        # Create treeview frame with inset shadow effect
        tree_frame = tk.Frame(left, bg=BRAND_SURFACE, relief='sunken', bd=3)
        tree_frame.pack(fill="both", expand=True, pady=(2, 0))
        
        # Create scrollbars
        tree_scroll_y = ttk.Scrollbar(tree_frame, orient="vertical")
        tree_scroll_y.pack(side="right", fill="y", padx=(0, 2), pady=2)
        
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal")
        tree_scroll_x.pack(side="bottom", fill="x", padx=2, pady=(0, 2))
        
        # Create the treeview table
        self.jobs = ttk.Treeview(
            tree_frame,
            columns=("property", "owner", "gallery", "progress", "status", "actions"),
            show="tree headings",
            height=10,
            yscrollcommand=tree_scroll_y.set,
            xscrollcommand=tree_scroll_x.set,
            style='Jobs.Treeview',   # NEW
        )
        
        # Configure scrollbars
        tree_scroll_y.config(command=self.jobs.yview)
        tree_scroll_x.config(command=self.jobs.xview)
        
        # Headings
        self.jobs.heading("#0", text="File", anchor="w")
        self.jobs.heading("property", text="Property", anchor="w")
        self.jobs.heading("owner", text="Owner", anchor="w")
        self.jobs.heading("gallery", text="Gallery", anchor="w")
        self.jobs.heading("progress", text="Progress", anchor="center")
        self.jobs.heading("status", text="Status", anchor="center")
        self.jobs.heading("actions", text="Actions", anchor="center")
        
        # Friendlier default column sizes
        self.jobs.column("#0",       width=360, minwidth=280, stretch=True,  anchor="w")
        self.jobs.column("property", width=320, minwidth=260, stretch=True,  anchor="w")
        self.jobs.column("owner",    width=180, minwidth=130, stretch=False, anchor="w")
        self.jobs.column("gallery",  width=160, minwidth=120, stretch=False, anchor="w")
        self.jobs.column("progress", width=110, minwidth= 90, stretch=False, anchor="center")
        self.jobs.column("status",   width=110, minwidth= 90, stretch=False, anchor="center")
        self.jobs.column("actions",  width=130, minwidth=110, stretch=False, anchor="center")
        
        # Auto-size on resize and show tooltips for truncated text
        self.jobs.bind("<Configure>", self._on_jobs_configure)
        self.jobs.bind("<Motion>", self._maybe_show_jobs_tooltip)
        self.jobs.bind("<Leave>", lambda e: self._hide_jobs_tooltip())
        
        # (Optional) Double-click header to autosize
        for cname in ("#0", "property"):
            self.jobs.heading(cname, command=lambda c=cname: self._autosize_job_columns())
        
        # Style the treeview
        self.jobs.tag_configure("queued", background=BRAND_SURFACE_LIGHT, foreground=BRAND_TEXT_SECONDARY)
        self.jobs.tag_configure("processing", background=BRAND_SURFACE_HOVER, foreground=BRAND_TEXT)
        self.jobs.tag_configure("completed", background=BRAND_SUCCESS, foreground="white")
        self.jobs.tag_configure("failed", background=BRAND_ERROR, foreground="white")
        
        self.jobs.pack(fill="both", expand=True, padx=2, pady=2)
        
        # Bind click handler for actions column
        self.jobs.bind("<ButtonRelease-1>", self._on_job_click)

        if DND_AVAILABLE:
            # Only register DND when the extension is present
            try:
                self.jobs.drop_target_register(DND_FILES)  # type: ignore[arg-type]
                self.jobs.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                # If anything goes wrong, silently disable DND
                pass
        else:
            # Provide a gentle hint that DND is disabled
            hint = tk.Label(left, text="Drag & drop disabled — install 'tkinterdnd2' to enable.", 
                          fg=BRAND_WARNING, bg=BRAND_BG)
            hint.pack(anchor="w", pady=(6, 0))

        # Right: log
        log_label = ttk.Label(right, text="Activity Log (double-click URLs to open)", style='Brand.TLabel')
        log_label.pack(anchor="w")

        # 3D inset log area with texture
        log_outer = tk.Frame(right, bg=BRAND_SURFACE, relief='sunken', bd=3)
        log_outer.pack(fill="both", expand=True, pady=(4, 0))
        
        log_frame = tk.Frame(log_outer, bg=BRAND_BORDER)
        log_frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        self.log = tk.Text(log_frame, state="disabled", wrap="word", height=6,
                          bg=BRAND_BG_GRADIENT, fg=BRAND_TEXT,
                          insertbackground=BRAND_TEXT,
                          relief="flat", bd=0, highlightthickness=0,
                          font=('Consolas', 11), padx=8, pady=8)
        self.log.pack(fill="both", expand=True, padx=1, pady=1)

        # Configure text tags for better readability
        self.log.tag_configure("link", foreground="#64B5F6", underline=1, font=('Consolas', 11, 'bold'))
        self.log.tag_configure("success", foreground=BRAND_SUCCESS_LIGHT, font=('Consolas', 11, 'bold'))
        self.log.tag_configure("error", foreground=BRAND_ERROR, font=('Consolas', 11, 'bold'))
        self.log.tag_configure("warning", foreground=BRAND_WARNING, font=('Consolas', 11))
        self.log.tag_configure("info", foreground=BRAND_SECONDARY_LIGHT, font=('Consolas', 11))
        self.log.tag_configure("highlight", background=BRAND_SURFACE_ELEVATED, foreground=BRAND_PRIMARY_LIGHT, font=('Consolas', 11, 'bold'))
        self.log.tag_configure("header", foreground=BRAND_PRIMARY_LIGHT, font=('Consolas', 12, 'bold'))
        self.log.tag_configure("separator", foreground=BRAND_TEXT_DIM, font=('Consolas', 10))
        self.log.tag_configure("property", foreground="#FFD700", font=('Consolas', 11, 'bold'))
        self.log.tag_configure("progress", foreground=BRAND_SECONDARY_LIGHT, font=('Consolas', 11))
        self.log.tag_bind("link", "<Double-Button-1>", self._on_link_click)
        self.log.tag_bind("link", "<Enter>", lambda e: self.log.config(cursor="hand2"))
        self.log.tag_bind("link", "<Leave>", lambda e: self.log.config(cursor=""))

        # Bottom: Enhanced 3D progress bar with glossy effect
        bar_outer = tk.Frame(right, bg=BRAND_SURFACE, relief='raised', bd=2)
        bar_outer.pack(fill="x", pady=(4, 0))
        
        bar_frame = ttk.Frame(bar_outer)
        bar_frame.pack(fill="x", expand=True, padx=2, pady=2)
        
        self.progress = ttk.Progressbar(bar_frame, orient="horizontal", mode="indeterminate", 
                                       style='Enhanced.Horizontal.TProgressbar')
        self.progress.pack(fill="x", expand=True)
        
        self.eta_var = tk.StringVar(value="✨ Ready to process")
        eta_label = tk.Label(right, textvariable=self.eta_var, 
                           bg=BRAND_BG, fg=BRAND_PRIMARY_LIGHT,
                           font=('Segoe UI', 10, 'bold'))
        eta_label.pack(anchor="w", pady=(4, 0))

        # Enhanced status bar with connection indicators
        self.status = tk.StringVar(value="✅ Ready")
        status_frame = tk.Frame(self, bg=BRAND_SURFACE, relief='raised', bd=1)
        status_frame.pack(fill="x", side="bottom")
        
        # Main status container
        status_container = tk.Frame(status_frame, bg=BRAND_SURFACE_ELEVATED)
        status_container.pack(fill="x")
        
        # Left side - connection status indicators
        self.conn_frame = tk.Frame(status_container, bg=BRAND_SURFACE_ELEVATED)
        self.conn_frame.pack(side="left", padx=10)
        
        # Portal status
        self.portal_status = tk.Label(self.conn_frame, text="⚪ Portal: Checking...", 
                                     bg=BRAND_SURFACE_ELEVATED, fg=BRAND_TEXT_DIM,
                                     font=('Segoe UI', 9))
        self.portal_status.pack(side="left", padx=(0, 15))
        
        # run_report status
        self.runreport_status = tk.Label(self.conn_frame, text="⚪ run_report: Checking...",
                                        bg=BRAND_SURFACE_ELEVATED, fg=BRAND_TEXT_DIM,
                                        font=('Segoe UI', 9))
        self.runreport_status.pack(side="left", padx=(0, 15))
        
        # API key status
        self.apikey_status = tk.Label(self.conn_frame, text="⚪ API Key: Checking...",
                                     bg=BRAND_SURFACE_ELEVATED, fg=BRAND_TEXT_DIM,
                                     font=('Segoe UI', 9))
        self.apikey_status.pack(side="left", padx=(0, 15))
        
        # Right side - main status text
        status_bar = tk.Label(status_container, textvariable=self.status, anchor="e",
                            bg=BRAND_SURFACE_ELEVATED, fg=BRAND_TEXT_SECONDARY,
                            font=('Segoe UI', 9), padx=10, pady=4)
        status_bar.pack(side="right", fill="x", expand=True)
        
        # Start status checks
        self.after(500, self._check_all_status)
        self.after(30000, self._start_status_timer)  # Start recurring checks after 30s

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
    
    def _on_jobs_configure(self, event=None):
        """Debounced autosize when the table resizes."""
        # Cancel prior pending autosize if any
        if hasattr(self, "_autosize_after_id") and self._autosize_after_id:
            try:
                self.after_cancel(self._autosize_after_id)
            except Exception:
                pass
        self._autosize_after_id = self.after(120, self._autosize_job_columns)
    
    def _autosize_job_columns(self, pad=24):
        """Auto width for File (#0) and Property columns, capped to 55% each."""
        try:
            fnt = tkFont.Font(font=('Segoe UI', 10))
        except Exception:
            fnt = tkFont.Font()
        tree = self.jobs
        table_w = max(1, tree.winfo_width() or tree.winfo_reqwidth())
        max_each = int(table_w * 0.55)
        
        cols = [
            ("#0",       280),  # (column id, minwidth)
            ("property", 260),
        ]
        
        for col, minw in cols:
            # Start with heading text width
            try:
                heading_text = tree.heading(col)["text"]
            except Exception:
                heading_text = ""
            w = fnt.measure(str(heading_text))
            
            # Measure all visible rows
            for iid in tree.get_children(""):
                txt = tree.item(iid, "text") if col == "#0" else tree.set(iid, col)
                w = max(w, fnt.measure(str(txt)))
            
            # Apply padding and bounds
            w = max(minw, min(w + pad, max_each))
            try:
                tree.column(col, width=w)
            except Exception:
                pass
    
    def _maybe_show_jobs_tooltip(self, event):
        """Show a tooltip with full text when a cell is truncated (File/Property)."""
        tree = self.jobs
        row = tree.identify_row(event.y)
        col_id = tree.identify_column(event.x)  # '#0', '#1', ...
        if not row:
            self._hide_jobs_tooltip()
            return
        
        # Only handle File (#0) and first data column (#1 -> 'property')
        if col_id not in ("#0", "#1"):
            self._hide_jobs_tooltip()
            return
        
        col_name = "#0" if col_id == "#0" else tree["columns"][0]  # 'property'
        text = tree.item(row, "text") if col_name == "#0" else tree.set(row, col_name)
        if not text:
            self._hide_jobs_tooltip()
            return
        
        # If the text actually fits, don't show a tooltip
        fnt = tkFont.Font(font=('Segoe UI', 10))
        text_px = fnt.measure(str(text))
        col_w = int(tree.column(col_name, "width"))
        if text_px <= col_w - 8:
            self._hide_jobs_tooltip()
            return
        
        # Create or update the tooltip
        x = event.x_root + 14
        y = event.y_root + 12
        tip = getattr(self, "_jobs_tip", None)
        if tip is None:
            tip = tk.Toplevel(self)
            tip.wm_overrideredirect(True)
            tip.wm_attributes("-topmost", True)
            lbl = tk.Label(tip, text=str(text), bg="#111", fg="#fff",
                           bd=1, relief="solid", font=('Segoe UI', 9), padx=6, pady=3)
            lbl.pack()
            self._jobs_tip = tip
        else:
            lbl = tip.winfo_children()[0]
            lbl.config(text=str(text))
        tip.geometry(f"+{x}+{y}")
    
    def _hide_jobs_tooltip(self):
        tip = getattr(self, "_jobs_tip", None)
        if tip is not None:
            try:
                tip.destroy()
            except Exception:
                pass
            self._jobs_tip = None
    
    def add_job_row(self, zip_path: Path, owner_name: str = "", gallery_name: str = ""):
        """Add a new job row to the treeview table"""
        # Derive property name from ZIP filename (spaces not underscores)
        property_name = zip_path.stem.replace('_', ' ')
        
        # Insert new row with initial values
        row_id = self.jobs.insert("", "end", 
                                  text=zip_path.name,
                                  values=(property_name, owner_name, gallery_name, "0%", "Queued", ""),
                                  tags=("queued",))
        
        # Store the mapping
        self.job_rows[zip_path] = row_id
        
        # Autosize columns after insert
        self._on_jobs_configure()
        
        return row_id

    def _add_paths(self, items):
        added = 0
        skipped = 0
        for p in items:
            try:
                path = Path(str(p).strip("{}"))
                
                # If path is a directory, zip it first
                if path.is_dir():
                    # Create tmp_zips directory structure
                    tmp_zip_dir = OUTPUT_DIR / "tmp_zips"
                    tmp_zip_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Create zip file with the folder name
                    zip_filename = f"{path.name}.zip"
                    zip_path = tmp_zip_dir / zip_filename
                    
                    # Create the zip file with compression
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        # Walk through the directory and add all files
                        for root, dirs, files in os.walk(path):
                            for file in files:
                                file_path = Path(root) / file
                                # Add file with relative path from the folder root
                                arcname = file_path.relative_to(path)
                                zipf.write(file_path, arcname)
                    
                    # Now treat the created zip as the path to add
                    path = zip_path
                    self._log_line(f"📁 Compressed folder to: {zip_filename}")
                
                # Process zip files (either original or just created from folder)
                if path.suffix.lower() == ".zip" and path.exists():
                    # Check for duplicates by comparing absolute paths
                    path_absolute = path.resolve()
                    is_duplicate = False
                    
                    for existing_path in self.zip_list:
                        if existing_path.resolve() == path_absolute:
                            is_duplicate = True
                            skipped += 1
                            break
                    
                    if not is_duplicate:
                        self.zip_list.append(path)
                        # Add row to the jobs table
                        owner_id, owner_display, owner_label = self._resolve_selected_owner()
                        owner_text = self.owner_display_by_id.get(owner_id, owner_label) if owner_id else owner_label
                        self.add_job_row(path, owner_name=owner_text, gallery_name="")
                        added += 1
            except Exception:
                continue
        
        # Provide detailed feedback about what happened
        if added and skipped:
            self._log_line(f"✅ Added {added} file{'s' if added > 1 else ''} • Skipped {skipped} duplicate{'s' if skipped > 1 else ''}")
        elif added:
            self._log_line(f"✅ Added {added} inspection file{'s' if added > 1 else ''}")
        elif skipped:
            self._log_line(f"⚠️ File already in list ({skipped} duplicate{'s' if skipped > 1 else ''} skipped)")
        else:
            self._log_line("ℹ️ No new files added")

    def clear_list(self):
        self.zip_list.clear()
        self.job_rows.clear()
        # Clear all items from the treeview
        for item in self.jobs.get_children():
            self.jobs.delete(item)
        self._log_line("🗑️ File list cleared")
    
    def _set_row(self, zip_path: Path, **cols):
        """Update specific columns in a job row.
        
        Args:
            zip_path: Path to the ZIP file
            **cols: Keyword arguments for columns to update:
                   owner, gallery, progress, status, actions
        """
        if zip_path not in self.job_rows:
            return
        
        row_id = self.job_rows[zip_path]
        
        # Get current values
        current_values = self.jobs.item(row_id, "values")
        if not current_values:
            return
        
        # Create list from current values (convert tuple to list)
        new_values = list(current_values)
        
        # Column indices mapping
        col_indices = {
            "property": 0,
            "owner": 1, 
            "gallery": 2,
            "progress": 3,
            "status": 4,
            "actions": 5
        }
        
        # Update specified columns
        for col_name, value in cols.items():
            if col_name in col_indices:
                new_values[col_indices[col_name]] = value
        
        # Determine appropriate tag based on status
        tag = "queued"
        if "status" in cols:
            status = cols["status"].lower()
            if "running" in status or "processing" in status:
                tag = "processing"
            elif "done" in status or "completed" in status:
                tag = "completed"
            elif "failed" in status or "error" in status:
                tag = "failed"
            elif "waiting" in status or "queued" in status:
                tag = "queued"
        
        # Update the row
        self.jobs.item(row_id, values=new_values, tags=(tag,))
        
        # Update actions whenever row changes
        self._update_actions_for(zip_path)
    
    def _update_actions_for(self, zip_path: Path):
        """Update the actions column based on job state."""
        with self._state_lock:
            state = self.jobs_state.get(zip_path, {})
        
        actions = []
        
        # If job has a report_id, can view in portal
        if state.get("report_id"):
            actions.append("View in Portal")
            actions.append("Copy Portal Link")
        
        # If job has output_dir, can open folder
        if state.get("output_dir"):
            actions.append("Open")
        
        # If job is not finished, can cancel
        if not state.get("finished"):
            actions.append("Cancel")
        
        # If job is finished and failed, can retry
        if state.get("finished") and state.get("return_code", 0) != 0:
            actions.append("Retry")
        
        # Update the actions column with available actions
        actions_text = " | ".join(actions) if actions else "..."
        
        if zip_path in self.job_rows:
            row_id = self.job_rows[zip_path]
            current_values = list(self.jobs.item(row_id, "values"))
            current_values[5] = actions_text  # Update actions column
            self.jobs.item(row_id, values=current_values)

    # ----- Job Control Methods -----
    
    def toggle_pause(self):
        """Toggle pause/resume for job processing."""
        if self.paused:
            self.pause_event.set()  # Resume
            self.paused = False
            self.pause_btn.config(text="⏸️ PAUSE")
            self._log_line("▶️ Processing resumed")
            self._set_status("🔄 Processing resumed...")
        else:
            self.pause_event.clear()  # Pause
            self.paused = True
            self.pause_btn.config(text="▶️ RESUME")
            self._log_line("⏸️ Processing paused (no new jobs will start)")
            self._set_status("⏸️ Paused - Click RESUME to continue")
    
    def _cancel_job(self, zip_path: Path):
        """Cancel a running job."""
        with self._state_lock:
            # Mark as canceled
            self.cancel_flags[zip_path] = True
            
            # Try to terminate the process
            proc = self.proc_map.get(zip_path)
            if proc:
                try:
                    if sys.platform == "win32":
                        # On Windows, try CTRL_BREAK_EVENT first, then terminate
                        try:
                            import signal
                            proc.send_signal(signal.CTRL_BREAK_EVENT)
                        except:
                            proc.terminate()
                    else:
                        # On Unix-like systems, use terminate
                        proc.terminate()
                    
                    self._log_line(f"⚠️ Canceling job: {zip_path.name}")
                    
                    # Update job state
                    state = self.jobs_state.get(zip_path, {})
                    state["finished"] = True
                    state["return_code"] = -2  # Special code for canceled
                    self.jobs_state[zip_path] = state
                    
                    # Update UI
                    self._set_row(zip_path, status="Canceled", progress="--")
                    
                except Exception as e:
                    self._log_line(f"❌ Error canceling job {zip_path.name}: {e}")
    
    def _retry_job(self, zip_path: Path):
        """Retry a failed or canceled job."""
        with self._state_lock:
            # Reset job state
            self.jobs_state[zip_path] = {
                "total": None, "done": 0, "start": None, 
                "finished": False, "report_id": None, 
                "output_dir": None, "return_code": None
            }
            
            # Clear cancel flag if set
            self.cancel_flags.pop(zip_path, None)
            
            # Update UI
            self._set_row(zip_path, status="Queued (Retry)", progress="0%")
        
        self._log_line(f"🔄 Retrying job: {zip_path.name}")
        
        # Launch worker thread for retry
        t = threading.Thread(
            target=self._run_one_zip_worker,
            args=(zip_path,),
            daemon=True
        )
        t.start()

    # ----- Actions -----
    def start(self):
        if not self.zip_list:
            messagebox.showwarning("No files", "Add or drop at least one ZIP.")
            return
        
        # Save settings when starting processing
        self.save_settings()
        
        # Validate owner selection
        owner_id, owner_display, owner_label = self._resolve_selected_owner()
        if not owner_id:
            messagebox.showerror("Owner Required", "Select a paid owner portal before generating reports.")
            self.owner_combo.focus()
            return

        portal_label = owner_label or owner_display or owner_id
        self._log_line(f"✅ Reports will be uploaded to portal: {portal_label}")

        # Property address will be automatically extracted from ZIP filename

        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            messagebox.showerror("API key missing", "OPENAI_API_KEY not found in .env.")
            return

        # Reset progress
        self._clear_progress()
        self._log_line("="*50)
        self._log_line(f"🚀 Starting inspection analysis")
        self._log_line(f"📋 Processing {len(self.zip_list)} property file{'s' if len(self.zip_list) > 1 else ''}")
        self._log_line(f"⚡ Speed: {JOB_CONCURRENCY}x parallel processing")
        self._log_line("="*50)
        self._set_status("🔄 Processing inspections...")

        # Orchestrator thread
        if self._orchestrator and self._orchestrator.is_alive():
            messagebox.showinfo("Already running", "Please wait for the current run to finish.")
            return

        # Enable pause button
        self.pause_btn.config(state="normal")
        self.paused = False
        self.pause_event.set()  # Start unpaused

        self._orchestrator = threading.Thread(
            target=self._run_all_parallel,
            daemon=True,
        )
        self._orchestrator.start()

    def open_output(self):
        # Try to open the most recent output directory
        most_recent_dir = None
        with self._state_lock:
            # Check parallel job states first
            for state in self.jobs_state.values():
                if state.get("output_dir"):
                    most_recent_dir = state["output_dir"]
            
            # If no parallel output, check sequential
            if not most_recent_dir and hasattr(self, 'last_output_dir'):
                most_recent_dir = self.last_output_dir
        
        if most_recent_dir:
            # Ensure we're not double-nesting the path
            if Path(most_recent_dir).is_absolute():
                # If it's already an absolute path, use it directly
                p = Path(most_recent_dir)
            else:
                # Otherwise, append to OUTPUT_DIR
                p = OUTPUT_DIR / most_recent_dir
            self._log_line(f"Opening specific output directory: {p}")
        else:
            p = OUTPUT_DIR
            self._log_line(f"Opening general output directory: {p}")
        
        p = p.resolve()
        self._log_line(f"Resolved path: {p}")
        
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
        """Open the CheckMyRental landing page with owner portal"""
        try:
            # Open the landing page which now includes the owner portal login
            webbrowser.open(portal_url("/"))
            self._log_line("🌐 Opening CheckMyRental Portal in browser...")
        except Exception as e:
            self._log_line(f"⚠️ Could not open portal: {e}")
    
    def refresh_owners(self):
        """Fetch available PAID owners from the API - only paid customers get reports"""
        # Also update status indicators when refreshing
        self._check_all_status()
        self.owner_id_map = {}
        self.owner_display_by_id = {}
        self.owner_details = {}

        try:
            # Fetch only PAID owners from the backend API
            # This ensures inspectors only see customers who have paid for service
            api_url = portal_url("/api/owners/paid-owners")
            self._log_line(f"🔍 Fetching paid owners from: {api_url}")
            response = requests.get(api_url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                owners = data.get("owners", [])
                
                if owners:
                    # Create display strings that show both name and owner_id
                    owner_display = []
                    self.owner_id_map = {}  # Store mapping of display name to owner_id
                    self.owner_details = {}  # Store full owner details
                    
                    for owner in owners:
                        name = owner.get("name", owner.get("full_name", ""))
                        owner_id = owner.get("owner_id", "")
                        is_paid = owner.get("is_paid", False)
                        
                        # Create display string with payment status
                        if name:
                            status_icon = "✅" if is_paid else "⚠️"
                            display = f"{status_icon} {name} ({owner_id})"
                            owner_display.append(display)
                            self.owner_id_map[display] = owner_id
                            self.owner_display_by_id[owner_id] = display
                            # Store full details
                            self.owner_details[owner_id] = owner
                        else:
                            owner_display.append(owner_id)
                            self.owner_id_map[owner_id] = owner_id
                            self.owner_display_by_id[owner_id] = owner_id
                            self.owner_details[owner_id] = owner
                    
                    values = [PLACEHOLDER_OWNER] + owner_display
                    self.owner_combo['values'] = values
                    self.owner_combo.set(PLACEHOLDER_OWNER)
                    self._apply_saved_owner_selection()
                    self._log_line(f"✅ Loaded {len(owners)} PAID customer(s)")
                    self._log_line("💰 Only paid customers appear in this list")
                else:
                    # No paid owners found
                    self.owner_combo['values'] = ["No paid customers yet"]
                    self._log_line("⚠️ No paid customers found - waiting for payments")
            else:
                # API not available, use defaults
                self._use_default_owners()
                
        except requests.exceptions.RequestException:
            # Network error or backend not running, use defaults
            self._use_default_owners()
        except Exception as e:
            self._log_line(f"⚠️ Could not load owners: {e}")
            self._use_default_owners()
    
    def _use_default_owners(self):
        """Fallback when no paid owners are available or API is down"""
        default_owners = [
            "⚠️ No Paid Customers Found",
            "Please check backend connection",
            "or wait for customers to pay"
        ]
        self.owner_id_map = {}
        self.owner_display_by_id = {}
        self.owner_details = {}
        self.owner_combo['values'] = [PLACEHOLDER_OWNER] + default_owners
        self.owner_combo.set(PLACEHOLDER_OWNER)
        self.owner_id_var.set('')
        self.pending_owner_id = ''
        self.pending_owner_display = ''
        self._log_line("⚠️ No paid customers found - customers must pay to receive reports")
        
    def _apply_saved_owner_selection(self):
        """Apply any saved owner selection after the dropdown is populated"""
        values = list(self.owner_combo['values']) if self.owner_combo['values'] else []
        if not values:
            return
        target_id = getattr(self, 'pending_owner_id', '').strip()
        target_display = getattr(self, 'pending_owner_display', '').strip()
        if target_id:
            display = self.owner_display_by_id.get(target_id)
            if display and display in values:
                self.owner_combo.set(display)
                self.owner_id_var.set(target_id)
                self.pending_owner_id = ''
                self.pending_owner_display = ''
                return
        if target_display and target_display in values:
            self.owner_combo.set(target_display)
            self.owner_id_var.set(self.owner_id_map.get(target_display, ''))
            self.pending_owner_id = ''
            self.pending_owner_display = ''
            return
        self.owner_combo.set(PLACEHOLDER_OWNER)
        self.owner_id_var.set('')

    def _resolve_selected_owner(self):
        """Return (owner_id, owner_display, owner_label) for the current selection"""
        owner_display = self.owner_var.get().strip()
        owner_id = self.owner_id_var.get().strip()
        if owner_display == PLACEHOLDER_OWNER:
            owner_display = ''
        details = getattr(self, 'owner_details', {}).get(owner_id, {}) if owner_id else {}
        owner_label = details.get('name') or details.get('full_name') or owner_display
        return owner_id, owner_display, owner_label


    def _on_owner_selected(self, event=None):
        """Auto-populate owner_id field when an owner is selected from dropdown"""
        selected = self.owner_var.get().strip()
        if selected == PLACEHOLDER_OWNER:
            self.owner_id_var.set('')
            self.pending_owner_id = ''
            self.pending_owner_display = ''
            return

        if selected in getattr(self, 'owner_id_map', {}):
            owner_id = self.owner_id_map[selected]
            self.owner_id_var.set(owner_id)
            self.pending_owner_id = owner_id
            self.pending_owner_display = selected

            details = getattr(self, 'owner_details', {}).get(owner_id, {})
            if details:
                self._log_line(f"✅ Selected: {details.get('name', 'Unknown')}")
                self._log_line(f"   📧 Email: {details.get('email', 'N/A')}")
                self._log_line(f"   📊 Status: {'✅ Paid' if details.get('is_paid') else '❌ Payment Required'}")
                self._log_line(f"   🏘️ Properties: {len(details.get('properties', []))}")
        else:
            self.owner_id_var.set('')
            self.pending_owner_id = ''
            self.pending_owner_display = ''

    # Gallery fetching method removed - not needed
    
    # ----- Status Checking Methods -----
    def _check_all_status(self):
        """Check all connection statuses"""
        self._check_portal_status()
        self._check_runreport_status()
        self._check_apikey_status()
    
    def _check_portal_status(self):
        """Check if the portal API is online"""
        try:
            api_url = portal_url("/api/owners/paid-owners")
            response = requests.get(api_url, timeout=3)
            if response.status_code == 200:
                data = response.json()
                num_paid = len(data.get("owners", []))
                self.portal_status.config(text=f"✅ Portal: {num_paid} Paid Owners", fg=BRAND_SUCCESS_LIGHT)
            else:
                self.portal_status.config(text="⚠️ Portal: Error", fg=BRAND_WARNING)
        except requests.exceptions.RequestException:
            self.portal_status.config(text="❌ Portal: Offline", fg=BRAND_ERROR)
        except Exception:
            self.portal_status.config(text="❌ Portal: Error", fg=BRAND_ERROR)
    
    def _check_runreport_status(self):
        """Check if run_report can be found"""
        dummy_path = Path("test.zip")
        cmd = _resolve_run_report_cmd(dummy_path)
        if cmd:
            self.runreport_status.config(text="✅ run_report: Found", fg=BRAND_SUCCESS_LIGHT)
        else:
            self.runreport_status.config(text="❌ run_report: Not Found", fg=BRAND_ERROR)
    
    def _check_apikey_status(self):
        """Check if API key is present"""
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if key:
            masked = f"{key[:6]}..." if len(key) > 6 else "Present"
            self.apikey_status.config(text=f"✅ API Key: {masked}", fg=BRAND_SUCCESS_LIGHT)
        else:
            self.apikey_status.config(text="❌ API Key: Missing", fg=BRAND_ERROR)
    
    def _start_status_timer(self):
        """Start recurring status checks every 30 seconds"""
        self._check_all_status()
        self.after(30000, self._start_status_timer)

    def _auto_refresh_owners(self):
        """Auto-refresh paid owners list every 30 seconds to catch new payments"""
        try:
            # Store current selection
            current_selection = self.owner_var.get()

            # Refresh the owners list
            self.refresh_owners()

            # Try to restore previous selection if it still exists
            if current_selection and current_selection in [self.owner_combo['values'][i] for i in range(len(self.owner_combo['values']))]:
                self.owner_var.set(current_selection)

            # Log that we checked for updates
            self._log_line("🔄 Auto-checking for new paid customers...")

        except Exception as e:
            # Silently fail - don't interrupt workflow
            pass

        # Schedule next refresh in 30 seconds
        self.after(30000, self._auto_refresh_owners)

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
        client_name = self.client_name_var.get().strip()  # Inspector name
        owner_id, owner_display, owner_label = self._resolve_selected_owner()
        property_address = ""  # Will be extracted from ZIP filename
        owner_arg = owner_label or owner_display or owner_id

        if not owner_id:
            self._log_line('⚠️ Owner ID missing - cannot upload report. Skipping job.')
            return

        display_for_row = owner_label or owner_display
        if display_for_row:
            self._set_row(zip_path, owner=display_for_row)

        if owner_label:
            self._log_line(f'🏠 Target Owner Portal: {owner_label}')
        else:
            if owner_display:
                self._log_line(f'🏠 Target Owner Portal: {owner_display}')
        self._log_line(f'🔑 Owner ID: {owner_id}')

        cmd = _resolve_run_report_cmd(zip_path, client_name, property_address, owner_arg, owner_id)
        if not cmd:
            self._log_line("ERROR: Could not locate run_report. Set RUN_REPORT_CMD or place run_report.py next to operator_ui.py")
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
                    rid = m_id.group(1)
                    with self._state_lock:
                        state = self.jobs_state.get(zip_path, {})
                        state["report_id"] = rid
                        self.jobs_state[zip_path] = state
                    owner_id, owner_display, owner_label = self._resolve_selected_owner()
                    if owner_id:
                        label_for_log = owner_label or owner_display or owner_id
                        self._log_line(f"[{zip_path.name}] 📤 Uploaded to {label_for_log}'s portal")
                    self._log_line(f"[{zip_path.name}] Interactive Report: {portal_url(f'/reports/{rid}')}")

                # OUTPUT_DIR
                m_dir = OUTPUT_DIR_RE.match(line)
                if m_dir:
                    output_dir = m_dir.group(1)
                    # Store it for open_output to use
                    with self._state_lock:
                        self.last_output_dir = output_dir

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
                    self._set_eta(f"✅ Done  •  {total_images}/{total_images}")
                self._log_line(f"✅ Completed: {zip_path.name}")
                if report_id:
                    owner_id, owner_display, owner_label = self._resolve_selected_owner()
                    if owner_id:
                        label_for_log = owner_label or owner_display or owner_id
                        self._log_line(f"[{zip_path.name}] 📤 Uploaded to {label_for_log}'s portal")
                    self._log_line(f"Interactive Report: {portal_url(f'/reports/{report_id}')}")
                    self._log_line('(Click the link to open in browser)')
            else:
                self._finish_progress()
                self._set_eta("Failed")
                self._log_line(f"❌ Failed ({rc}): {zip_path.name}")

        except Exception as e:
            self._finish_progress()
            self._set_eta("Error")
            self._log_line(f"ERROR running {zip_path.name}: {e}")

    # ----- Parallel path -----
    def _run_all_parallel(self):
        # Reset shared job state
        with self._state_lock:
            self.jobs_state = {p: {"total": None, "done": 0, "start": None, "finished": False, "report_id": None, "output_dir": None, "return_code": None}
                               for p in self.zip_list}
        
        # Update initial status to "Waiting" for all jobs
        for zip_path in self.zip_list:
            self._set_row(zip_path, status="Waiting", progress="")
        
        self._start_indeterminate("Analyzing (parallel)…")

        # Launch workers with a bounded pool
        sem = threading.Semaphore(JOB_CONCURRENCY)
        workers = []

        def launch(zip_path: Path):
            # Wait if paused before acquiring semaphore
            self.pause_event.wait()
            
            # Check if job was canceled before starting
            if self.cancel_flags.get(zip_path, False):
                return
            
            with sem:
                self._run_one_zip_worker(zip_path)

        for p in self.zip_list:
            t = threading.Thread(target=launch, args=(p,), daemon=True)
            workers.append(t)
            t.start()

        for t in workers:
            t.join()
        
        # Disable pause button when done
        self.pause_btn.config(state="disabled")

        # Show completion status
        self._log_line("")
        self._log_line("="*50)
        totals = [st for st in self.jobs_state.values()]
        global_total = sum((st.get("total") or 0) for st in totals)
        global_done = sum(st.get("done", 0) for st in totals)
        successful_jobs = sum(1 for st in totals if st.get("finished"))
        
        self._log_line(f"✅ ALL REPORTS COMPLETED SUCCESSFULLY!")
        self._log_line(f"📊 Total: {successful_jobs} report(s) generated")
        self._log_line(f"📸 Images: {global_done}/{global_total} processed")
        self._log_line("="*50)
        
        # Update UI to show completion with visual feedback
        self._set_status("✅ All reports generated successfully!")
        self._set_eta(f"✅ COMPLETED  •  {successful_jobs} reports  •  {global_total} images")
        self._finish_progress()
        
        # Flash the window to get attention
        self.after(100, lambda: self.bell())
        self.after(200, lambda: self.lift())
        self.after(300, lambda: self.focus_force())
        
        # Play a subtle completion sound if available (Windows)
        try:
            if sys.platform == "win32":
                import winsound
                winsound.MessageBeep(winsound.MB_OK)
        except:
            pass
        
        # Auto-open output folder after a short delay
        self.after(1000, self.open_output)

    def _run_one_zip_worker(self, zip_path: Path):
        client_name = self.client_name_var.get().strip()  # Inspector name
        owner_id, owner_display, owner_label = self._resolve_selected_owner()
        gallery = getattr(self, 'selected_gallery', '')  # Gallery name
        property_address = ""  # Will be extracted from ZIP filename
        owner_arg = owner_label or owner_display or owner_id

        if not owner_id:
            self._log_line('⚠️ Owner ID missing - cannot upload report. Skipping job.')
            with self._state_lock:
                st = self.jobs_state.get(zip_path, {})
                st['finished'] = True
                self.jobs_state[zip_path] = st
            return

        if owner_label:
            self._set_row(zip_path, owner=owner_label)
            self._log_line(f'🏠 Target Owner Portal: {owner_label}')
        else:
            self._set_row(zip_path, owner=owner_display)
            if owner_display:
                self._log_line(f'🏠 Target Owner Portal: {owner_display}')
        if gallery:
            self._set_row(zip_path, gallery=gallery)
            self._log_line(f'🎞️ Gallery: {gallery}')
        self._log_line(f'🔑 Owner ID: {owner_id}')

        cmd = _resolve_run_report_cmd(zip_path, client_name, property_address, owner_arg, owner_id, gallery)
        if not cmd:
            self._log_line("ERROR: Could not locate run_report. Set RUN_REPORT_CMD or place run_report.py next to operator_ui.py")
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
            
            # Store process in map for potential cancellation
            with self._state_lock:
                self.proc_map[zip_path] = proc

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
                    owner_id, owner_display, owner_label = self._resolve_selected_owner()
                    if owner_id:
                        label_for_log = owner_label or owner_display or owner_id
                        self._log_line(f"[{zip_path.name}] 📤 Uploaded to {label_for_log}'s portal")
                    self._log_line(f"[{zip_path.name}] Interactive Report: {portal_url(f'/reports/{rid}')}")

                # OUTPUT_DIR to track where files were saved
                m_dir = OUTPUT_DIR_RE.match(line)
                if m_dir:
                    output_dir = m_dir.group(1)
                    with self._state_lock:
                        state = self.jobs_state.get(zip_path, {})
                        state["output_dir"] = output_dir
                        self.jobs_state[zip_path] = state

            rc = proc.wait()
            with self._state_lock:
                # Remove from process map
                if zip_path in self.proc_map:
                    del self.proc_map[zip_path]
                st = self.jobs_state.get(zip_path, {})
                st["finished"] = True
                st["return_code"] = rc  # Track return code for status
                self.jobs_state[zip_path] = st

            if rc == 0:
                self._log_line(f"✅ Completed: {zip_path.name}")
            else:
                self._log_line(f"❌ Failed ({rc}): {zip_path.name}")

        except Exception as e:
            self._log_line(f"ERROR running {zip_path.name}: {e}")
            with self._state_lock:
                # Remove from process map
                if zip_path in self.proc_map:
                    del self.proc_map[zip_path]
                st = self.jobs_state.get(zip_path, {})
                st["finished"] = True
                st["return_code"] = -1  # Mark as failed due to exception
                self.jobs_state[zip_path] = st

    # ----- Progress helpers -----
    def _clear_progress(self):
        def _do():
            self.progress.stop()
            self.progress.configure(mode="indeterminate", maximum=100, value=0)
            self.eta_var.set("✨ Ready to process")
            # Reset progress bar color to default
            self.style.configure('Enhanced.Horizontal.TProgressbar',
                               background=BRAND_PRIMARY,
                               lightcolor=BRAND_PRIMARY_LIGHT)
        self.after(0, _do)

    def _start_indeterminate(self, status_text="Working…"):
        def _do():
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
            self.status.set(status_text)
            self.eta_var.set("🔄 Processing...")
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
            self.eta_var.set(f"⏱️ ~{remaining}s  •  📸 {idx_img}/{total_images} photos")
        self.after(0, _do)

    def _set_eta(self, text: str):
        self.after(0, lambda: self.eta_var.set(text))

    def _finish_progress(self):
        def _do():
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=100, value=100)
            # Set progress bar to green to indicate completion
            self.style.configure('Enhanced.Horizontal.TProgressbar',
                               background=BRAND_SUCCESS,
                               lightcolor=BRAND_SUCCESS_LIGHT)
        self.after(0, _do)

    def _set_status(self, text: str):
        self.after(0, lambda: self.status.set(text))

    # ----- Aggregator for parallel mode -----
    def _poll_parallel_progress(self):
        """Every 250 ms, compute a global progress/ETA across parallel jobs and update the bar."""
        try:
            with self._state_lock:
                states_copy = dict(self.jobs_state)
                states = list(states_copy.values())
            
            # Update individual job rows in the table
            for zip_path, state in states_copy.items():
                # Determine status
                if state.get("finished"):
                    # Check return code to determine if it failed
                    rc = state.get("return_code", 0)
                    if rc == 0:
                        # Add checkmark if report is ready
                        if state.get("report_id"):
                            status = "✅ Done"
                        else:
                            status = "Done"
                        progress_str = "100%"
                    else:
                        status = "Failed"
                        # Show how far it got before failing
                        if state.get("total") and state.get("done"):
                            pct = (state.get("done", 0) / state["total"]) * 100
                            progress_str = f"{pct:.0f}%"
                        else:
                            progress_str = "0%"
                elif state.get("start"):
                    status = "Running"
                    # Calculate progress percentage if total is known
                    if state.get("total"):
                        pct = (state.get("done", 0) / state["total"]) * 100
                        progress_str = f"{pct:.0f}%"
                    else:
                        progress_str = ""
                else:
                    status = "Waiting"
                    progress_str = ""
                
                # Update the row
                self._set_row(zip_path, progress=progress_str, status=status)
            
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
                        self._set_eta(f"⏱️ ~{remaining}s  •  📸 {global_done}/{global_total}  •  {len(running)} active")
                    else:
                        self._set_eta(f"{global_done}/{global_total}")
                # else: remain indeterminate until totals are known

                # When all jobs finished, show Done
                if states and all(s.get("finished") for s in states):
                    if global_total > 0:
                        self._set_eta(f"✅ ALL REPORTS COMPLETED  •  {global_total}/{global_total} images processed")
                        self._finish_progress()
                        self._set_status("✅ All reports generated successfully!")
                    else:
                        self._set_eta("✅ Processing complete")
                        self._finish_progress()
                        self._set_status("✅ Reports generated!")
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
                
                # Apply formatting based on message content
                tag = self._get_message_tag(line)
                
                # Format the message for better readability
                formatted_line = self._format_message(line)

                # Turn URLs into clickable links
                parts = self._linkify(formatted_line)
                for seg_text, seg_tag in parts:
                    if seg_tag == "link":
                        start_idx = self.log.index("end-1c")
                        self.log.insert("end", seg_text, ("link", f"url:{seg_text}"))
                    else:
                        # Apply the appropriate tag based on message type
                        if tag:
                            self.log.insert("end", seg_text, tag)
                        else:
                            self.log.insert("end", seg_text)

                self.log.insert("end", "\\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._pump_logs)

    def _get_message_tag(self, line: str):
        """Determine the appropriate tag for a log message based on its content."""
        line_lower = line.lower()
        
        # Check for different message types
        if "✅" in line or "completed" in line_lower or "success" in line_lower or "done" in line_lower:
            return "success"
        elif "❌" in line or "error" in line_lower or "failed" in line_lower:
            return "error"
        elif "⚠️" in line or "warning" in line_lower or "skipped" in line_lower:
            return "warning"
        elif "📤" in line or "📊" in line or "📸" in line or "🏠" in line or "🔑" in line:
            return "info"
        elif "===" in line:
            return "header"
        elif "---" in line or "___" in line:
            return "separator"
        elif ".zip" in line_lower and "→" in line:
            return "property"
        elif re.search(r"\[\d+/\d+\]", line) or "elapsed" in line_lower or "eta" in line_lower:
            return "progress"
        elif "interactive report:" in line_lower:
            return "highlight"
        elif "starting" in line_lower or "analyzing" in line_lower:
            return "info"
        
        return None
    
    def _format_message(self, line: str):
        """Format a log message for better human readability."""
        # Remove excessive technical details
        formatted = line
        
        # Simplify file paths - show only filename for ZIP files
        if ".zip" in line and "/" in line or "\\" in line:
            # Extract just the filename from full paths
            zip_pattern = r'([^/\\]+\.zip)'
            match = re.search(zip_pattern, line)
            if match and not "→" in line:  # Don't modify lines that already show property mapping
                filename = match.group(1)
                formatted = re.sub(r'[^\s]+\.zip', filename, formatted)
        
        # Clean up progress indicators
        if "[" in formatted and "]" in formatted and "elapsed" in formatted:
            # Make progress more readable: "[3/12] IMG_0042.jpg | elapsed 38s  ETA ~72s"
            # becomes: "📸 Processing image 3 of 12 • Time: 38s • Remaining: ~72s"
            progress_match = re.match(r'\[([^]]+)\]\s*\[(\d+)/(\d+)\]\s*([^\|]+)\|\s*elapsed\s*(\d+)s\s*ETA\s*~(\d+)s', formatted)
            if progress_match:
                zip_name = progress_match.group(1)
                current = progress_match.group(2)
                total = progress_match.group(3)
                img_name = progress_match.group(4).strip()
                elapsed = progress_match.group(5)
                eta = progress_match.group(6)
                formatted = f"📸 [{zip_name}] Processing image {current}/{total} • Time: {elapsed}s • Remaining: ~{eta}s"
        
        # Simplify technical messages
        replacements = {
            "REPORT_ID=": "📄 Report ID: ",
            "OUTPUT_DIR=": "📁 Saved to: ",
            "Starting analysis of": "🔍 Analyzing",
            "images in total": "total images",
            "ERROR:": "❌ Error:",
            "WARNING:": "⚠️ Warning:",
            "INFO:": "ℹ️ ",
        }
        
        for old, new in replacements.items():
            formatted = formatted.replace(old, new)
        
        # Add spacing around important sections
        if "===" in formatted:
            formatted = f"\n{formatted}\n"
        
        return formatted
    
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
    
    def _on_job_click(self, event):
        """Handle clicks on job rows in the treeview"""
        # Get the clicked item
        item = self.jobs.identify('item', event.x, event.y)
        column = self.jobs.identify('column', event.x, event.y)
        
        if not item:
            return
        
        # Get the values for this row
        values = self.jobs.item(item, 'values')
        if not values or len(values) < 6:
            return
        
        # Check if actions column was clicked (column #6)
        if column == '#6':
            actions = values[5]  # Actions is the 6th column (index 5)
            
            # Find the corresponding zip_path for this row
            zip_path = None
            for path, row_id in self.job_rows.items():
                if row_id == item:
                    zip_path = path
                    break
            
            if not zip_path:
                return
            
            # Show context menu with available actions
            if any(action in actions for action in ["View in Portal", "Copy Portal Link", "Open", "Cancel", "Retry"]):
                menu = tk.Menu(self, tearoff=0)
                
                if "View in Portal" in actions:
                    menu.add_command(label="View in Portal", command=lambda: self._view_report(zip_path))
                
                if "Copy Portal Link" in actions:
                    menu.add_command(label="Copy Portal Link", command=lambda: self._copy_portal_link(zip_path))
                
                if "Open" in actions:
                    menu.add_command(label="Open Folder", command=lambda: self._open_job_folder(zip_path))
                
                if "Cancel" in actions:
                    menu.add_command(label="Cancel Job", command=lambda: self._cancel_job(zip_path))
                
                if "Retry" in actions:
                    menu.add_command(label="Retry Job", command=lambda: self._retry_job(zip_path))
                
                menu.post(event.x_root, event.y_root)
    
    def _view_report(self, zip_path: Path):
        """View the report in the portal"""
        with self._state_lock:
            state = self.jobs_state.get(zip_path, {})
            report_id = state.get("report_id")
        
        if report_id:
            url = portal_url(f'/reports/{report_id}')
            webbrowser.open(url)
            self._log_line(f"🌐 Opening report for {zip_path.name} in browser...")
    
    def _copy_portal_link(self, zip_path: Path):
        """Copy the portal link to clipboard"""
        with self._state_lock:
            state = self.jobs_state.get(zip_path, {})
            report_id = state.get("report_id")
        
        if report_id:
            url = portal_url(f'/reports/{report_id}')
            # Copy to clipboard
            self.clipboard_clear()
            self.clipboard_append(url)
            self._log_line(f"📋 Portal link copied to clipboard for {zip_path.name}")
    
    def _open_job_folder(self, zip_path: Path):
        """Open the output folder for a specific job"""
        with self._state_lock:
            state = self.jobs_state.get(zip_path, {})
            output_dir = state.get("output_dir")
        
        if output_dir:
            p = Path(output_dir) if Path(output_dir).is_absolute() else OUTPUT_DIR / output_dir
            try:
                if sys.platform == "win32":
                    startfile = getattr(os, "startfile", None)
                    if callable(startfile):
                        startfile(str(p))
                    else:
                        subprocess.run(["explorer", str(p)])
                elif sys.platform == "darwin":
                    subprocess.run(["open", str(p)])
                else:
                    subprocess.run(["xdg-open", str(p)])
                self._log_line(f"📁 Opened output folder for {zip_path.name}")
            except Exception as e:
                self._log_line(f"⚠️ Could not open folder: {e}")
    
    def _create_header(self):
        """Create modern CheckMyRental header with gradient and depth"""
        # Create header with shadow effect - significantly increased height
        header_shadow = tk.Frame(self, bg=BRAND_SHADOW, height=110)
        header_shadow.pack(fill="x")
        header_shadow.pack_propagate(False)
        
        header = tk.Frame(header_shadow, bg=BRAND_SURFACE_ELEVATED, height=105, relief='raised', bd=2)
        header.pack(fill="x", padx=(0, 0), pady=(0, 5))
        header.pack_propagate(False)
        
        # Main container with gradient background simulation
        brand_frame = tk.Frame(header, bg=BRAND_SURFACE_ELEVATED)
        brand_frame.pack(expand=True, pady=15)
        
        # Logo and text container with depth
        logo_container = tk.Frame(brand_frame, bg=BRAND_SURFACE_ELEVATED)
        logo_container.pack()
        
        # Logo with 3D effect and subtle animation
        logo_frame = tk.Frame(logo_container, bg=BRAND_SURFACE_ELEVATED, relief='raised', bd=2)
        logo_frame.pack(side="left", padx=(0, 20))
        
        # Logo canvas with shadow effect - MUCH larger size
        logo_canvas = tk.Canvas(logo_frame, width=72, height=72, bg=BRAND_SURFACE_ELEVATED, highlightthickness=0)
        logo_canvas.pack(padx=3, pady=3)
        
        # Draw the rotated square house with 3D depth
        # Create rotated square for house body with shadow - MUCH larger
        house_size = 46
        cx, cy = 36, 36  # Center point adjusted for much larger canvas
        
        # Calculate corners of rotated square (45 degrees)
        import math
        angle = math.radians(45)
        half_size = house_size / 2
        
        # Rotated square points
        points = []
        for dx, dy in [(-half_size, 0), (0, -half_size), (half_size, 0), (0, half_size)]:
            x = cx + dx * math.cos(angle) - dy * math.sin(angle)
            y = cy + dx * math.sin(angle) + dy * math.cos(angle)
            points.extend([x, y])
        
        # Draw house shadow first
        shadow_points = [p + 2 if i % 2 else p + 2 for i, p in enumerate(points)]
        logo_canvas.create_polygon(shadow_points, fill="#404040", outline="")
        
        # Draw house (rotated square) with gradient effect
        logo_canvas.create_polygon(points, fill="#2c3e50", outline="#34495e", width=1)
        
        # Draw window grid (4 panes) - much larger
        window_size = 16
        wx, wy = cx, cy - 3
        
        # White background for window
        logo_canvas.create_rectangle(wx - window_size/2, wy - window_size/2, 
                                    wx + window_size/2, wy + window_size/2,
                                    fill="white", outline="")
        
        # Window cross lines - thicker for larger size
        logo_canvas.create_line(wx, wy - window_size/2, wx, wy + window_size/2, 
                               fill="#2c3e50", width=3)
        logo_canvas.create_line(wx - window_size/2, wy, wx + window_size/2, wy,
                               fill="#2c3e50", width=3)
        
        # Red checkmark circle with glow (bottom right) - much larger
        circle_r = 14
        circle_x, circle_y = 54, 54
        
        # Glow effect with graduated colors
        glow_colors = ["#ff9999", "#ff7777", "#ff5555"]
        for i in range(3):
            glow_r = circle_r + (3 - i) * 2
            logo_canvas.create_oval(circle_x - glow_r, circle_y - glow_r,
                                   circle_x + glow_r, circle_y + glow_r,
                                   fill='', outline=glow_colors[i], width=1)
        
        # Main circle
        self.logo_circle = logo_canvas.create_oval(circle_x - circle_r, circle_y - circle_r,
                                                  circle_x + circle_r, circle_y + circle_r,
                                                  fill=BRAND_PRIMARY, outline=BRAND_PRIMARY_LIGHT, width=1)
        
        # White checkmark with enhanced visibility - much larger
        logo_canvas.create_line(46, 54, 50, 58, fill="white", width=4, capstyle="round")
        logo_canvas.create_line(50, 58, 60, 48, fill="white", width=4, capstyle="round")
        
        # Company name with enhanced typography and depth
        name_frame = tk.Frame(logo_container, bg=BRAND_SURFACE_ELEVATED)
        name_frame.pack(side="left")
        
        # Main title with text shadow effect
        title_frame = tk.Frame(name_frame, bg=BRAND_SURFACE_ELEVATED)
        title_frame.pack(anchor="w")
        
        # Create text with shadow effect - MUCH larger font
        check_shadow = tk.Label(title_frame, text="Check", 
                              font=('Segoe UI Light', 36, 'bold'),
                              bg=BRAND_SURFACE_ELEVATED, fg="#2a2a2a")
        check_shadow.place(x=3, y=3)
        
        check_label = tk.Label(title_frame, text="Check", 
                             font=('Segoe UI Light', 36, 'bold'),
                             bg=BRAND_SURFACE_ELEVATED, fg=BRAND_TEXT)
        check_label.pack(side="left")
        
        my_label = tk.Label(title_frame, text="My",
                          font=('Segoe UI Semibold', 36, 'bold'),
                          bg=BRAND_SURFACE_ELEVATED, fg=BRAND_TEXT)
        my_label.pack(side="left")
        
        rental_label = tk.Label(title_frame, text="Rental",
                              font=('Segoe UI Semibold', 36, 'bold'),
                              bg=BRAND_SURFACE_ELEVATED, fg=BRAND_PRIMARY_LIGHT)
        rental_label.pack(side="left")
        
        # Professional tagline with subtle animation
        tagline_label = tk.Label(
            name_frame,
            text="Inspector Portal  •  Professional Property Reports",
            font=('Segoe UI', 13, 'italic'),
            bg=BRAND_SURFACE_ELEVATED,
            fg=BRAND_TEXT_SECONDARY
        )
        tagline_label.pack(anchor="w", pady=(4, 0))
        
        # Add subtle pulsing animation to logo
        self.logo_pulse_state = 0
        self.animate_logo(logo_canvas, cx, cy)
    
    def animate_logo(self, canvas, cx, cy):
        """Add subtle pulsing animation to logo for premium feel"""
        self.logo_pulse_state = (self.logo_pulse_state + 1) % 60
        
        # Calculate pulse scale (subtle breathing effect)
        scale = 1.0 + 0.02 * math.sin(self.logo_pulse_state * math.pi / 30)
        
        # Update logo circle with pulse (if it exists)
        if hasattr(self, 'logo_circle'):
            try:
                # Subtle color pulse for the checkmark circle
                intensity = int(20 + 10 * math.sin(self.logo_pulse_state * math.pi / 30))
                pulse_color = f"#{hex(231 + intensity)[2:]}{hex(76)[2:]}{hex(60)[2:]}"
                canvas.itemconfig(self.logo_circle, fill=pulse_color)
            except:
                pass
        
        # Continue animation
        self.after(50, lambda: self.animate_logo(canvas, cx, cy))
    
    # ----- Settings Persistence Methods -----
    def load_and_apply_settings(self):
        """Load settings from JSON file and apply them to the UI"""
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                
                # Apply loaded settings to UI fields
                self.pending_owner_display = settings.get('owner_name', '').strip()
                self.pending_owner_id = settings.get('owner_id', '').strip()
                if self.pending_owner_display:
                    self.owner_var.set(self.pending_owner_display)
                else:
                    self.owner_combo.set(PLACEHOLDER_OWNER)
                    self.owner_id_var.set('')


                if 'inspector_name' in settings:
                    self.client_name_var.set(settings['inspector_name'])
                
                # Apply concurrency settings if present
                global JOB_CONCURRENCY, ANALYSIS_CONCURRENCY
                if 'job_concurrency' in settings:
                    JOB_CONCURRENCY = max(1, settings['job_concurrency'])
                    if hasattr(self, 'job_concurrency_var'):
                        self.job_concurrency_var.set(JOB_CONCURRENCY)
                if 'analysis_concurrency' in settings:
                    ANALYSIS_CONCURRENCY = max(1, settings['analysis_concurrency'])
                    if hasattr(self, 'analysis_concurrency_var'):
                        self.analysis_concurrency_var.set(ANALYSIS_CONCURRENCY)
                
                # Update speed label with loaded values
                if hasattr(self, 'speed_label'):
                    self.speed_label.config(text=f"⚡ Fast Processing ({JOB_CONCURRENCY}×{ANALYSIS_CONCURRENCY})")
                
                self._log_line(f"✅ Settings loaded from {SETTINGS_FILE.name}")
        except Exception as e:
            # Settings load failed, use defaults
            self._log_line(f"ℹ️ No previous settings found, using defaults")
    
    def update_concurrency(self):
        """Update concurrency values and speed label when spinners change"""
        global JOB_CONCURRENCY, ANALYSIS_CONCURRENCY
        JOB_CONCURRENCY = self.job_concurrency_var.get()
        ANALYSIS_CONCURRENCY = self.analysis_concurrency_var.get()
        
        # Update speed label if it exists
        if hasattr(self, 'speed_label'):
            self.speed_label.config(text=f"⚡ Fast Processing ({JOB_CONCURRENCY}×{ANALYSIS_CONCURRENCY})")
    
    def save_settings(self):
        """Save current UI field values to JSON file"""
        try:
            settings = {
                'owner_name': self.owner_var.get().strip(),
                'owner_id': self.owner_id_var.get().strip(),
                # owner_id is automatically determined from dropdown selection
                'inspector_name': self.client_name_var.get().strip(),
                'job_concurrency': self.job_concurrency_var.get() if hasattr(self, 'job_concurrency_var') else JOB_CONCURRENCY,
                'analysis_concurrency': self.analysis_concurrency_var.get() if hasattr(self, 'analysis_concurrency_var') else ANALYSIS_CONCURRENCY
            }
            
            # Don't save placeholder text
            if settings['owner_name'] == PLACEHOLDER_OWNER:
                settings['owner_name'] = ''
                settings['owner_id'] = ''
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
            
            return True
        except Exception as e:
            # Silently fail to save settings
            return False
    
    def on_closing(self):
        """Handle window close event"""
        self.save_settings()
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()
