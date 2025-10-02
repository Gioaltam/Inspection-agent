    
    def show_preflight_modal(self):
        """Show a modal dialog with preflight check details before processing."""
        # Create modal window
        modal = tk.Toplevel(self)
        modal.title("Preflight Check - Confirm Processing")
        modal.transient(self)
        modal.grab_set()
        
        # Configure modal appearance
        modal.configure(bg=BRAND_BG)
        modal.resizable(False, False)
        
        # Center the modal
        modal_width = 800
        modal_height = 600
        x = (modal.winfo_screenwidth() // 2) - (modal_width // 2)
        y = (modal.winfo_screenheight() // 2) - (modal_height // 2)
        modal.geometry(f'{modal_width}x{modal_height}+{x}+{y}')
        
        # Header
        header_frame = tk.Frame(modal, bg=BRAND_SURFACE_ELEVATED, relief='raised', bd=2)
        header_frame.pack(fill="x", padx=10, pady=(10, 0))
        
        header_label = tk.Label(header_frame, text="✅ Preflight Check",
                               font=('Segoe UI', 16, 'bold'),
                               bg=BRAND_SURFACE_ELEVATED, fg=BRAND_TEXT)
        header_label.pack(pady=10)
        
        # Main content frame with scrollbar
        main_frame = tk.Frame(modal, bg=BRAND_BG)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create canvas and scrollbar for scrollable content
        canvas = tk.Canvas(main_frame, bg=BRAND_SURFACE, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=BRAND_SURFACE)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Validation flags
        has_errors = False
        error_messages = []
        
        # Check OPENAI_API_KEY
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            has_errors = True
            error_messages.append("❌ OPENAI_API_KEY not found in .env file")
        
        # Check run_report availability
        test_path = self.zip_list[0] if self.zip_list else Path("test.zip")
        run_report_cmd = _resolve_run_report_cmd(test_path)
        if not run_report_cmd:
            has_errors = True
            error_messages.append("❌ run_report.py not found - please ensure it's in the same directory")
        
        # Get owner and gallery information
        owner_name = self.owner_var.get().strip()
        if owner_name == "Select or type owner name...":
            owner_name = ""
        
        gallery_name = self.gallery_var.get().strip()
        if gallery_name in ["Select gallery...", "Select an owner first"]:
            gallery_name = ""
        elif gallery_name == "+ Create new gallery...":
            gallery_name = "[New Gallery]"
        
        owner_id = self.owner_id_var.get().strip()
        
        # Display errors if any
        if has_errors:
            error_frame = ttk.LabelFrame(scrollable_frame, text="⚠️ Issues Found", 
                                        padding=10, style='Brand.TLabelframe')
            error_frame.pack(fill="x", padx=10, pady=(10, 10))
            
            for error_msg in error_messages:
                error_label = tk.Label(error_frame, text=error_msg,
                                     font=('Segoe UI', 10),
                                     bg=BRAND_SURFACE, fg=BRAND_ERROR,
                                     anchor="w", justify="left")
                error_label.pack(fill="x", pady=2)
            
            # Add guidance
            guidance_frame = ttk.LabelFrame(scrollable_frame, text="💡 How to Fix", 
                                          padding=10, style='Brand.TLabelframe')
            guidance_frame.pack(fill="x", padx=10, pady=(0, 10))
            
            if not api_key:
                tk.Label(guidance_frame, 
                        text="1. Create a .env file in the same directory as this app\n"
                             "2. Add: OPENAI_API_KEY=your-api-key-here\n"
                             "3. Save the file and restart the app",
                        font=('Segoe UI', 9), bg=BRAND_SURFACE, fg=BRAND_TEXT_SECONDARY,
                        anchor="w", justify="left").pack(fill="x", pady=2)
            
            if not run_report_cmd:
                tk.Label(guidance_frame,
                        text="1. Ensure run_report.py is in the same directory as operator_ui.py\n"
                             "2. Or set RUN_REPORT_CMD environment variable",
                        font=('Segoe UI', 9), bg=BRAND_SURFACE, fg=BRAND_TEXT_SECONDARY,
                        anchor="w", justify="left").pack(fill="x", pady=2)
        
        # Job details section
        jobs_frame = ttk.LabelFrame(scrollable_frame, text="📋 Job Details", 
                                   padding=10, style='Brand.TLabelframe')
        jobs_frame.pack(fill="both", expand=True, padx=10, pady=(10, 10))
        
        # Summary information
        summary_text = f"Total Jobs: {len(self.zip_list)}\n"
        if owner_name:
            summary_text += f"Target Owner: {owner_name}\n"
        else:
            summary_text += "Target Owner: [Local Only - No Upload]\n"
        
        if gallery_name:
            summary_text += f"Gallery: {gallery_name}\n"
        
        if owner_id:
            summary_text += f"Owner ID: {owner_id}\n"
        
        summary_label = tk.Label(jobs_frame, text=summary_text,
                               font=('Segoe UI', 10, 'bold'),
                               bg=BRAND_SURFACE, fg=BRAND_TEXT,
                               anchor="w", justify="left")
        summary_label.pack(fill="x", pady=(0, 10))
        
        # Create table for ZIP files
        table_frame = tk.Frame(jobs_frame, bg=BRAND_SURFACE)
        table_frame.pack(fill="both", expand=True)
        
        # Table headers
        headers = ["Property Address", "File Size (MB)", "Est. Images", "Target"]
        header_frame = tk.Frame(table_frame, bg=BRAND_SURFACE_HOVER)
        header_frame.pack(fill="x")
        
        for i, header in enumerate(headers):
            label = tk.Label(header_frame, text=header,
                           font=('Segoe UI', 10, 'bold'),
                           bg=BRAND_SURFACE_HOVER, fg=BRAND_TEXT,
                           padx=10, pady=5)
            if i == 0:
                label.pack(side="left", fill="x", expand=True)
            else:
                label.pack(side="left", width=120)
        
        # ZIP file details
        total_size_mb = 0
        total_images = 0
        
        for zip_path in self.zip_list:
            row_frame = tk.Frame(table_frame, bg=BRAND_SURFACE, relief='ridge', bd=1)
            row_frame.pack(fill="x", pady=1)
            
            # Extract property address from filename
            property_address = zip_path.stem.replace('_', ' ')
            
            # Get file size
            try:
                file_size_bytes = zip_path.stat().st_size
                file_size_mb = file_size_bytes / (1024 * 1024)
                total_size_mb += file_size_mb
            except:
                file_size_mb = 0
            
            # Fast estimate of image count without extraction
            estimated_images = 0
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
                    for file_info in zf.namelist():
                        if any(file_info.lower().endswith(ext) for ext in image_extensions):
                            estimated_images += 1
                total_images += estimated_images
            except Exception as e:
                estimated_images = "Error"
            
            # Determine target
            if owner_name and gallery_name:
                target = f"{owner_name}/{gallery_name}"
            elif owner_name:
                target = owner_name
            else:
                target = "Local Only"
            
            # Create row cells
            tk.Label(row_frame, text=property_address,
                    font=('Segoe UI', 9), bg=BRAND_SURFACE, fg=BRAND_TEXT,
                    anchor="w", padx=10, pady=3).pack(side="left", fill="x", expand=True)
            
            tk.Label(row_frame, text=f"{file_size_mb:.1f}",
                    font=('Segoe UI', 9), bg=BRAND_SURFACE, fg=BRAND_TEXT_SECONDARY,
                    width=15, anchor="center").pack(side="left")
            
            tk.Label(row_frame, text=str(estimated_images),
                    font=('Segoe UI', 9), bg=BRAND_SURFACE, fg=BRAND_TEXT_SECONDARY,
                    width=15, anchor="center").pack(side="left")
            
            tk.Label(row_frame, text=target,
                    font=('Segoe UI', 9), bg=BRAND_SURFACE, fg=BRAND_PRIMARY_LIGHT,
                    width=15, anchor="center").pack(side="left")
        
        # Total summary
        total_frame = tk.Frame(jobs_frame, bg=BRAND_SURFACE_ELEVATED, relief='raised', bd=1)
        total_frame.pack(fill="x", pady=(10, 0))
        
        total_text = f"Total: {len(self.zip_list)} jobs, {total_size_mb:.1f} MB, ~{total_images} images"
        tk.Label(total_frame, text=total_text,
                font=('Segoe UI', 11, 'bold'),
                bg=BRAND_SURFACE_ELEVATED, fg=BRAND_PRIMARY_LIGHT,
                pady=5).pack()
        
        # Pack canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Button frame
        button_frame = tk.Frame(modal, bg=BRAND_BG)
        button_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        # Store modal reference for callbacks
        self.preflight_modal = modal
        
        # Cancel button
        cancel_btn = ttk.Button(button_frame, text="Cancel", 
                              command=lambda: self.cancel_preflight(modal),
                              style='Secondary.TButton')
        cancel_btn.pack(side="right", padx=(5, 0))
        
        # Start button (disabled if errors)
        start_btn = ttk.Button(button_frame, text="✨ Start Processing",
                             command=lambda: self.confirm_preflight(modal),
                             style='Success.TButton')
        start_btn.pack(side="right")
        
        if has_errors:
            start_btn.config(state="disabled")
            # Add warning text
            tk.Label(button_frame, 
                    text="⚠️ Please fix the issues above before starting",
                    font=('Segoe UI', 10, 'italic'),
                    bg=BRAND_BG, fg=BRAND_WARNING).pack(side="left")
        
        # Focus modal
        modal.focus_set()
    
    def cancel_preflight(self, modal):
        """Cancel the preflight modal and return to main window."""
        modal.destroy()
        self._log_line("ℹ️ Processing cancelled by user")
    
    def confirm_preflight(self, modal):
        """Confirm preflight and start processing."""
        modal.destroy()
        self.continue_with_processing()
