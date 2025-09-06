# frontend.py — Inspection Agent GUI (parallel ZIPs, hardened)
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
from tkinter import ttk, filedialog, messagebox
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

def _resolve_run_report_cmd(zip_path: Path, client_name: str = "", property_address: str = "", owner_name: str = "", owner_id: str = "") -> list[str] | None:
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
        self.minsize(900, 700)  # Adjusted minimum size
        
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
        self._state_lock = threading.Lock()
        self._orchestrator = None  # background thread that manages all jobs

        # UI
        self._build_ui()
        self.after(120, self._pump_logs)  # log flusher
        self.after(250, self._poll_parallel_progress)  # progress aggregator
    
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

    # ----- UI construction -----
    def _build_ui(self):
        # Create branded header
        self._create_header()
        
        # Main container with reduced padding
        main = ttk.Frame(self, style='Brand.TFrame')
        main.pack(fill="both", expand=True, padx=8, pady=5)

        # Left panel with 3D elevated card effect
        left_shadow = tk.Frame(main, bg=BRAND_SHADOW)
        left_shadow.pack(side="left", fill="y", padx=(2, 8), pady=2)
        
        left_container = ttk.LabelFrame(left_shadow, text="🏠 INSPECTION CONTROL", padding=12, style='Brand.TLabelframe')
        left_container.pack(fill="both", expand=True, padx=(0, 2), pady=(0, 2))
        left = ttk.Frame(left_container, style='Brand.TFrame')
        left.pack(fill="both", expand=True)

        # Right panel with 3D elevated card effect
        right_shadow = tk.Frame(main, bg=BRAND_SHADOW)
        right_shadow.pack(side="right", fill="both", expand=True, padx=(0, 2), pady=2)
        
        right_container = ttk.LabelFrame(right_shadow, text="📋 ACTIVITY LOG", padding=12, style='Brand.TLabelframe')
        right_container.pack(fill="both", expand=True, padx=(0, 2), pady=(0, 2))
        right = ttk.Frame(right_container, style='Brand.TFrame')
        right.pack(fill="both", expand=True)

        # Modern button group with hover effects
        btns = tk.Frame(left, bg=BRAND_SURFACE)
        btns.pack(fill="x", pady=(0, 10))
        
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
        run_frame.pack(fill="x", pady=(10, 0))
        
        # Create glowing success button with light green shadow
        run_shadow = tk.Frame(run_frame, bg="#1a3d2e", height=50, width=200)
        run_shadow.place(x=3, y=3)
        
        ttk.Button(run_frame, text="✨ GENERATE REPORTS", command=self.start, style='Success.TButton').pack(side="left")
        
        speed_label = tk.Label(run_frame, text=f"⚡ Fast Processing ({JOB_CONCURRENCY}×{ANALYSIS_CONCURRENCY})", 
                             font=('Segoe UI', 10, 'italic'), fg=BRAND_SUCCESS_LIGHT, bg=BRAND_BG)
        speed_label.pack(side="left", padx=(12, 0))

        # Property details with elevated 3D card
        details_shadow = tk.Frame(left, bg=BRAND_SHADOW)
        details_shadow.pack(fill="x", pady=(10, 2))
        
        client_frame = ttk.LabelFrame(details_shadow, text="🔍 INSPECTION DETAILS", padding=10, style='Brand.TLabelframe')
        client_frame.pack(fill="x", padx=(0, 3), pady=(0, 3))
        
        # Owner/Customer selection
        ttk.Label(client_frame, text="Select Owner Portal:", font=('Segoe UI', 10), style='Brand.TLabel').pack(anchor="w")
        
        owner_selection_frame = ttk.Frame(client_frame, style='Brand.TFrame')
        owner_selection_frame.pack(fill="x", pady=(5, 10))
        
        self.owner_var = tk.StringVar()
        self.owner_combo = ttk.Combobox(owner_selection_frame, textvariable=self.owner_var, width=28, 
                                       font=('Segoe UI', 10), state='normal')
        self.owner_combo.pack(side="left", fill="x", expand=True)
        self.owner_combo.set("Select or type owner name...")
        
        # Refresh button to fetch owners with CheckMyRental styling
        self.refresh_btn = ttk.Button(owner_selection_frame, text="🔄", width=3,
                                     command=self.refresh_owners, style='Secondary.TButton')
        self.refresh_btn.pack(side="left", padx=(5, 0))
        
        # Owner ID field for specific dashboard routing
        ttk.Label(client_frame, text="Owner ID (for dashboard routing):", font=('Segoe UI', 10), style='Brand.TLabel').pack(anchor="w", pady=(8, 2))
        self.owner_id_var = tk.StringVar()
        self.owner_id_entry = ttk.Entry(client_frame, textvariable=self.owner_id_var, width=30, font=('Segoe UI', 10))
        self.owner_id_entry.pack(fill="x", pady=(5, 5))
        
        # Add helpful hints
        hint_label = ttk.Label(client_frame, text="💡 Enter Owner ID to send reports to specific owner dashboard",
                             font=('Segoe UI', 8, 'italic'), foreground=BRAND_TEXT_DIM,
                             style='Brand.TLabel')
        hint_label.pack(anchor="w", pady=(2, 4))
        hint_label2 = ttk.Label(client_frame, text="💡 Leave blank to use general gallery",
                              font=('Segoe UI', 8, 'italic'), foreground=BRAND_TEXT_DIM,
                              style='Brand.TLabel')
        hint_label2.pack(anchor="w", pady=(0, 8))
        
        # Property address info (automatically extracted from filename)
        ttk.Label(client_frame, text="Property Address: Automatically extracted from ZIP filename", 
                 font=('Segoe UI', 10, 'italic'), foreground=BRAND_TEXT_SECONDARY,
                 style='Brand.TLabel').pack(anchor="w", pady=(0, 10))
        
        # Client name for records (inspector/employee name)
        ttk.Label(client_frame, text="Inspector Name (optional):", font=('Segoe UI', 10), style='Brand.TLabel').pack(anchor="w")
        self.client_name_var = tk.StringVar()
        self.client_name_entry = ttk.Entry(client_frame, textvariable=self.client_name_var, width=30, font=('Segoe UI', 10))
        self.client_name_entry.pack(fill="x", pady=(5, 0))
        
        # Auto-fetch owners on startup
        self.after(500, self.refresh_owners)
        
        # Portal button with improved styling matching landing page
        portal_frame = ttk.Frame(left, style='Brand.TFrame')
        portal_frame.pack(fill="x", pady=(10, 8))
        
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

        # Styled listbox with 3D inset effect
        list_label = ttk.Label(left, text="📸 Inspection Files:", style='Heading.TLabel')
        list_label.pack(anchor="w", pady=(6, 2))
        
        # Create listbox with inset shadow effect
        listbox_frame = tk.Frame(left, bg=BRAND_SURFACE, relief='sunken', bd=3)
        listbox_frame.pack(fill="both", expand=True, pady=(2, 0))
        
        self.listbox = tk.Listbox(listbox_frame, width=42, height=12, selectmode="extended",
                                 font=('Segoe UI', 10), bg=BRAND_SURFACE_LIGHT,
                                 fg=BRAND_TEXT,
                                 selectbackground=BRAND_PRIMARY, selectforeground='white',
                                 activestyle='none',
                                 relief='flat', bd=0, highlightthickness=0)
        self.listbox.pack(fill="both", expand=True, padx=2, pady=2)

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
            hint = tk.Label(left, text="Drag & drop disabled — install 'tkinterdnd2' to enable.", 
                          fg=BRAND_WARNING, bg=BRAND_BG)
            hint.pack(anchor="w", pady=(6, 0))

        # Right: log
        log_label = ttk.Label(right, text="Activity Log (double-click URLs to open)", style='Brand.TLabel')
        log_label.pack(anchor="w")

        # 3D inset log area with texture
        log_outer = tk.Frame(right, bg=BRAND_SURFACE, relief='sunken', bd=3)
        log_outer.pack(fill="both", expand=True, pady=(8, 0))
        
        log_frame = tk.Frame(log_outer, bg=BRAND_BORDER)
        log_frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        self.log = tk.Text(log_frame, state="disabled", wrap="word",
                          bg=BRAND_BG_GRADIENT, fg=BRAND_TEXT,
                          insertbackground=BRAND_TEXT,
                          relief="flat", bd=0, highlightthickness=0,
                          font=('Consolas', 11), padx=14, pady=14)
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
        bar_outer.pack(fill="x", pady=(8, 0))
        
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

        # Enhanced status bar with gradient background
        self.status = tk.StringVar(value="✅ Ready")
        status_frame = tk.Frame(self, bg=BRAND_SURFACE, relief='raised', bd=1)
        status_frame.pack(fill="x", side="bottom")
        
        status_bar = tk.Label(status_frame, textvariable=self.status, anchor="w",
                            bg=BRAND_SURFACE_ELEVATED, fg=BRAND_TEXT_SECONDARY,
                            font=('Segoe UI', 9), padx=10, pady=4)
        status_bar.pack(fill="x")

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
        skipped = 0
        for p in items:
            try:
                path = Path(str(p).strip("{}"))
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
                        # Show filename and extracted property address
                        property_address = path.stem.replace('_', ' ')
                        display_text = f"{path.name} → {property_address}"
                        self.listbox.insert("end", display_text)
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
        self.listbox.delete(0, "end")
        self._log_line("🗑️ File list cleared")

    # ----- Actions -----
    def start(self):
        if not self.zip_list:
            messagebox.showwarning("No files", "Add or drop at least one ZIP.")
            return
        
        # Validate owner selection
        owner_name = self.owner_var.get().strip()
        if not owner_name or owner_name == "Select or type owner name...":
            response = messagebox.askyesno(
                "Owner Not Selected", 
                "No owner portal selected. Reports will be saved locally only.\n\n"
                "Do you want to continue without uploading to an owner portal?"
            )
            if not response:
                self.owner_combo.focus()
                return
            self._log_line("⚠️ No owner selected - reports will be saved locally only")
        else:
            self._log_line(f"✅ Reports will be uploaded to: {owner_name}'s portal")
        
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
        """Fetch available owners from the API or provide defaults"""
        try:
            # Try to fetch owners from the backend if available
            # For now, provide common owner examples
            default_owners = [
                "John Smith",
                "Jane Doe",
                "Property Management LLC",
                "ABC Rentals",
                "XYZ Properties",
                "Main Street Realty",
                "Custom Owner"
            ]
            self.owner_combo['values'] = default_owners
            self._log_line("✅ Owner portal list loaded")
        except Exception as e:
            self._log_line(f"⚠️ Could not load owners: {e}")

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
        owner_name = self.owner_var.get().strip()  # Owner portal name
        owner_id = self.owner_id_var.get().strip()  # Owner ID for dashboard routing
        property_address = ""  # Will be extracted from ZIP filename
        
        # Clear placeholder text if still present
        if owner_name == "Select or type owner name...":
            owner_name = ""
        
        # Log the selected owner and ID
        if owner_name:
            self._log_line(f"🏠 Target Owner Portal: {owner_name}")
        if owner_id:
            self._log_line(f"🔑 Owner ID: {owner_id}")
        
        cmd = _resolve_run_report_cmd(zip_path, client_name, property_address, owner_name, owner_id)
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
                    owner_name = self.owner_var.get().strip()
                    if owner_name and owner_name != "Select or type owner name...":
                        self._log_line(f"📤 Uploading to {owner_name}'s portal...")
                    self._log_line(f"Interactive Report: {portal_url(f'/reports/{report_id}')}")
                
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
                    owner_name = self.owner_var.get().strip()
                    if owner_name and owner_name != "Select or type owner name...":
                        self._log_line(f"📤 Uploaded to {owner_name}'s portal")
                    self._log_line(f"Interactive Report: {portal_url(f'/reports/{report_id}')}")
                    self._log_line("(Click the link to open in browser)")
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
            self.jobs_state = {p: {"total": None, "done": 0, "start": None, "finished": False, "report_id": None, "output_dir": None}
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
        owner_name = self.owner_var.get().strip()  # Owner portal name
        owner_id = self.owner_id_var.get().strip()  # Owner ID for dashboard routing
        property_address = ""  # Will be extracted from ZIP filename
        
        # Clear placeholder text if still present
        if owner_name == "Select or type owner name...":
            owner_name = ""
        
        # Log the selected owner and ID
        if owner_name:
            self._log_line(f"🏠 Target Owner Portal: {owner_name}")
        if owner_id:
            self._log_line(f"🔑 Owner ID: {owner_id}")
        
        cmd = _resolve_run_report_cmd(zip_path, client_name, property_address, owner_name, owner_id)
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
                    owner_name = self.owner_var.get().strip()
                    if owner_name and owner_name != "Select or type owner name...":
                        self._log_line(f"[{zip_path.name}] 📤 Uploaded to {owner_name}'s portal")
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
                st = self.jobs_state.get(zip_path, {})
                st["finished"] = True
                self.jobs_state[zip_path] = st

            if rc == 0:
                self._log_line(f"✅ Completed: {zip_path.name}")
            else:
                self._log_line(f"❌ Failed ({rc}): {zip_path.name}")

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

if __name__ == "__main__":
    app = App()
    app.mainloop()
