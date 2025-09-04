#!/usr/bin/env python3
"""
Enhanced Frontend with API Integration
Connects to backend gallery for automatic report upload
"""

import os
import sys
import threading
import subprocess
import queue
import time
import re
import json
import webbrowser
from pathlib import Path
from datetime import datetime

# GUI
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Import API integration
from api_integration import ReportWorkflow, InspectionAPIClient

# Attempt drag & drop support
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    BaseTk = TkinterDnD.Tk
    DND_AVAILABLE = True
except:
    BaseTk = tk.Tk
    DND_FILES = None
    DND_AVAILABLE = False

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except:
    pass

APP_TITLE = "Inspection Agent - Enhanced"
OUTPUT_DIR = Path("workspace/outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Configuration
BACKEND_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")
EMPLOYEE_ID = os.getenv("EMPLOYEE_ID", "employee_001")


class EnhancedInspectionApp(BaseTk):
    """Enhanced inspection app with backend integration"""
    
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("900x700")
        
        # Initialize API client and workflow
        self.api_client = InspectionAPIClient(BACKEND_URL)
        self.workflow = ReportWorkflow(self.api_client)
        
        # Processing state
        self.processing_queue = queue.Queue()
        self.log_queue = queue.Queue()
        self.current_job = None
        
        # Setup UI
        self._setup_ui()
        
        # Start worker thread
        self.worker_thread = threading.Thread(target=self._process_worker, daemon=True)
        self.worker_thread.start()
        
        # Start log pump
        self.after(100, self._pump_logs)
        
    def _setup_ui(self):
        """Build the user interface"""
        
        # Main container
        main_frame = ttk.Frame(self, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)
        main_frame.columnconfigure(0, weight=1)
        
        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        ttk.Label(header_frame, text="Property Inspection Report Generator", 
                 font=("Helvetica", 14, "bold")).pack(side="left")
        
        # Employee info
        ttk.Label(header_frame, text=f"Employee: {EMPLOYEE_ID}", 
                 font=("Helvetica", 10)).pack(side="right", padx=(20, 0))
        
        # Input section
        input_frame = ttk.LabelFrame(main_frame, text="Property Information", padding="10")
        input_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        input_frame.columnconfigure(1, weight=1)
        
        # Client name
        ttk.Label(input_frame, text="Client Name:").grid(row=0, column=0, sticky="w", pady=5)
        self.client_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.client_var, width=40).grid(row=0, column=1, sticky="ew", pady=5)
        
        # Property address
        ttk.Label(input_frame, text="Property Address:").grid(row=1, column=0, sticky="w", pady=5)
        self.address_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.address_var, width=40).grid(row=1, column=1, sticky="ew", pady=5)
        
        # File selection
        ttk.Label(input_frame, text="Photos ZIP:").grid(row=2, column=0, sticky="w", pady=5)
        self.file_var = tk.StringVar()
        file_entry = ttk.Entry(input_frame, textvariable=self.file_var, width=40)
        file_entry.grid(row=2, column=1, sticky="ew", pady=5, padx=(0, 5))
        
        ttk.Button(input_frame, text="Browse...", 
                  command=self._browse_file).grid(row=2, column=2, pady=5)
        
        # Process button
        self.process_btn = ttk.Button(input_frame, text="Process & Upload to Gallery", 
                                     command=self._process_inspection)
        self.process_btn.grid(row=3, column=0, columnspan=3, pady=10)
        
        # Progress section
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="10")
        progress_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        progress_frame.columnconfigure(0, weight=1)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, 
                                           maximum=100, length=400)
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=5)
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(progress_frame, textvariable=self.status_var).grid(row=1, column=0, sticky="w")
        
        # Log section
        log_frame = ttk.LabelFrame(main_frame, text="Activity Log", padding="10")
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        
        # Create log with scrollbar
        log_container = ttk.Frame(log_frame)
        log_container.grid(row=0, column=0, sticky="nsew")
        log_container.rowconfigure(0, weight=1)
        log_container.columnconfigure(0, weight=1)
        
        self.log_text = tk.Text(log_container, height=15, width=80, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        
        scrollbar = ttk.Scrollbar(log_container, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.config(yscrollcommand=scrollbar.set)
        
        # Configure text tags for formatting
        self.log_text.tag_config("info", foreground="black")
        self.log_text.tag_config("success", foreground="green")
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("link", foreground="blue", underline=True)
        
        # Bind link clicking
        self.log_text.tag_bind("link", "<Button-1>", self._on_link_click)
        
        # Enable drag and drop if available
        if DND_AVAILABLE:
            self._setup_drag_drop(file_entry)
            
        # Button panel
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        
        ttk.Button(button_frame, text="Open Output Folder", 
                  command=self._open_output_folder).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Clear Log", 
                  command=self._clear_log).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Settings", 
                  command=self._show_settings).pack(side="right", padx=5)
    
    def _setup_drag_drop(self, widget):
        """Enable drag and drop for file selection"""
        def on_drop(event):
            files = self.tk.splitlist(event.data)
            if files:
                self.file_var.set(files[0])
                self._log("File dropped: " + Path(files[0]).name, "info")
        
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind('<<Drop>>', on_drop)
    
    def _browse_file(self):
        """Open file browser for ZIP selection"""
        filename = filedialog.askopenfilename(
            title="Select Photos ZIP",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")]
        )
        if filename:
            self.file_var.set(filename)
    
    def _process_inspection(self):
        """Process inspection and upload to gallery"""
        # Validate inputs
        if not self.client_var.get():
            messagebox.showerror("Error", "Please enter client name")
            return
        
        if not self.address_var.get():
            messagebox.showerror("Error", "Please enter property address")
            return
        
        if not self.file_var.get() or not Path(self.file_var.get()).exists():
            messagebox.showerror("Error", "Please select a valid ZIP file")
            return
        
        # Add to processing queue
        job = {
            'zip_path': Path(self.file_var.get()),
            'client_name': self.client_var.get(),
            'property_address': self.address_var.get(),
            'timestamp': datetime.now()
        }
        
        self.processing_queue.put(job)
        self.process_btn.config(state="disabled")
        self.status_var.set("Processing...")
        self._log(f"Starting inspection for {job['property_address']}", "info")
    
    def _process_worker(self):
        """Worker thread for processing inspections"""
        while True:
            try:
                job = self.processing_queue.get(timeout=1)
                self.current_job = job
                
                # Update UI
                self._update_status("Processing photos...")
                self._update_progress(0)
                
                # Process the inspection
                self._log(f"Analyzing photos from {job['zip_path'].name}", "info")
                
                result = self.workflow.process_and_upload(
                    source_path=job['zip_path'],
                    client_name=job['client_name'],
                    property_address=job['property_address'],
                    employee_id=EMPLOYEE_ID
                )
                
                # Handle results
                if result['status'] == 'success':
                    self._log(f"✓ Report uploaded successfully!", "success")
                    self._log(f"Report ID: {result['report_id']}", "info")
                    self._log(f"Gallery URL: {result['gallery_url']}", "link")
                    self._update_status("Complete - Report uploaded to gallery")
                    self._update_progress(100)
                    
                    # Optionally open gallery in browser
                    if messagebox.askyesno("Success", 
                                          "Report uploaded! Open client gallery?"):
                        webbrowser.open(result['gallery_url'])
                        
                elif result['status'] == 'partial':
                    self._log(f"⚠ Report generated but upload failed", "error")
                    self._log(f"Error: {result['error']}", "error")
                    self._log(f"PDF saved locally: {result['pdf_path']}", "info")
                    self._update_status("Partial - Report saved locally")
                    
                else:
                    self._log(f"✗ Processing failed: {result['error']}", "error")
                    self._update_status("Failed")
                
                self.current_job = None
                self.process_btn.config(state="normal")
                
            except queue.Empty:
                continue
            except Exception as e:
                self._log(f"Worker error: {str(e)}", "error")
                self.current_job = None
                self.process_btn.config(state="normal")
                self._update_status("Error")
    
    def _update_status(self, text):
        """Update status in UI thread"""
        self.status_var.set(text)
    
    def _update_progress(self, value):
        """Update progress bar"""
        self.progress_var.set(value)
    
    def _log(self, message, tag="info"):
        """Add message to log queue"""
        self.log_queue.put((message, tag))
    
    def _pump_logs(self):
        """Process log messages from queue"""
        try:
            while True:
                message, tag = self.log_queue.get_nowait()
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                self.log_text.config(state="normal")
                self.log_text.insert("end", f"[{timestamp}] ", "info")
                self.log_text.insert("end", message + "\n", tag)
                self.log_text.see("end")
                self.log_text.config(state="disabled")
        except queue.Empty:
            pass
        
        self.after(100, self._pump_logs)
    
    def _on_link_click(self, event):
        """Handle link clicks in log"""
        index = self.log_text.index("@%s,%s" % (event.x, event.y))
        tag_indices = self.log_text.tag_ranges("link")
        
        for i in range(0, len(tag_indices), 2):
            if self.log_text.compare(index, ">=", tag_indices[i]) and \
               self.log_text.compare(index, "<=", tag_indices[i+1]):
                url = self.log_text.get(tag_indices[i], tag_indices[i+1])
                webbrowser.open(url)
                break
    
    def _clear_log(self):
        """Clear the activity log"""
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
    
    def _open_output_folder(self):
        """Open the output folder in file explorer"""
        if sys.platform == "win32":
            os.startfile(OUTPUT_DIR)
        elif sys.platform == "darwin":
            subprocess.run(["open", OUTPUT_DIR])
        else:
            subprocess.run(["xdg-open", OUTPUT_DIR])
    
    def _show_settings(self):
        """Show settings dialog"""
        settings_window = tk.Toplevel(self)
        settings_window.title("Settings")
        settings_window.geometry("400x300")
        
        frame = ttk.Frame(settings_window, padding="20")
        frame.pack(fill="both", expand=True)
        
        ttk.Label(frame, text="Backend API URL:").grid(row=0, column=0, sticky="w", pady=5)
        api_var = tk.StringVar(value=self.api_client.base_url)
        ttk.Entry(frame, textvariable=api_var, width=40).grid(row=0, column=1, pady=5)
        
        ttk.Label(frame, text="Employee ID:").grid(row=1, column=0, sticky="w", pady=5)
        emp_var = tk.StringVar(value=EMPLOYEE_ID)
        ttk.Entry(frame, textvariable=emp_var, width=40).grid(row=1, column=1, pady=5)
        
        def save_settings():
            self.api_client.base_url = api_var.get()
            # Could save to config file here
            settings_window.destroy()
        
        ttk.Button(frame, text="Save", command=save_settings).grid(row=2, column=0, columnspan=2, pady=20)


def main():
    """Run the enhanced inspection app"""
    app = EnhancedInspectionApp()
    app.mainloop()


if __name__ == "__main__":
    main()