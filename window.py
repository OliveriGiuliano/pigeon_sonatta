# window.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import atexit
import os
import threading
import time

from video import VideoManager  # Your VLC wrapper
from audio import AudioGenerator  # Your audio generator

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Video-to-MIDI Generator")
        self.geometry("900x700")

        # VLC manager will be initialized once we have the video panel
        self.vlc_manager = None
        self.current_video_path = None
        
        # Audio generator
        self.audio_generator = None
        self.audio_enabled = False
        self.current_soundfont = None
        
        # Grid settings
        self.grid_width = 4
        self.grid_height = 3
        self.note_range = (50, 62)
        
        # Frame processing
        self.frame_processing_thread = None
        self.stop_frame_processing = False
        
        # UI Variables
        self.audio_enabled_var = tk.BooleanVar(value=False)

        self._create_menu()
        self._create_main_layout()
        self._create_status_bar()

        self._update_grid_overlay()
        
        # Initialize audio generator
        self._init_audio_generator()
        
        # Register cleanup
        atexit.register(self.cleanup)

    def _create_menu(self):
        menubar = tk.Menu(self)
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        for label in ["New Project", "Open Project", "Save Project", "Save Project As", None, "Exit"]:
            if label:
                file_menu.add_command(label=label, command=self._menu_action)
            else:
                file_menu.add_separator()
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Input menu
        input_menu = tk.Menu(menubar, tearoff=0)
        input_menu.add_command(label="Video File", command=self.open_video)
        input_menu.add_command(label="Camera", command=self._menu_action)
        input_menu.add_command(label="Input Settings", command=self._menu_action)
        menubar.add_cascade(label="Input", menu=input_menu)
        
        # Output menu
        output_menu = tk.Menu(menubar, tearoff=0)
        output_menu.add_command(label="Virtual MIDI Port", command=self._menu_action)
        output_menu.add_command(label="Save MIDI File", command=self._menu_action)
        output_menu.add_command(label="Record MIDI", command=self._menu_action)
        output_menu.add_separator()
        output_menu.add_checkbutton(label="Enable Audio Playback", variable=self.audio_enabled_var, command=self.toggle_audio)
        output_menu.add_command(label="Select Soundfont", command=self.select_soundfont)
        output_menu.add_command(label="Audio Device", command=self._menu_action)
        menubar.add_cascade(label="Output", menu=output_menu)
        
        # Presets menu
        presets_menu = tk.Menu(menubar, tearoff=0)
        presets_menu.add_command(label="Load Preset", command=self._menu_action)
        presets_menu.add_command(label="Save Preset", command=self._menu_action)
        presets_menu.add_command(label="Manage Presets", command=self._menu_action)
        presets_menu.add_separator()
        presets_menu.add_command(label="Factory Reset", command=self._menu_action)
        menubar.add_cascade(label="Presets", menu=presets_menu)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Show Visual Feedback", command=self._menu_action)
        view_menu.add_command(label="Show Filter Preview", command=self._menu_action)
        view_menu.add_command(label="Fullscreen Video", command=self._menu_action)
        menubar.add_cascade(label="View", menu=view_menu)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self._menu_action)
        help_menu.add_command(label="Documentation", command=self._menu_action)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    def _create_main_layout(self):
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Video display frame - now split into video and grid
        self.video_frame = ttk.Frame(paned, relief=tk.SUNKEN)
        self.video_frame.config(width=500, height=400)
        self.video_frame.pack_propagate(False)
        paned.add(self.video_frame, weight=3)
        
        # Split the video frame vertically
        video_paned = ttk.Panedwindow(self.video_frame, orient=tk.VERTICAL)
        video_paned.pack(fill=tk.BOTH, expand=True)
        
        # Top part: VLC video panel (70% of height)
        self.video_panel = ttk.Frame(video_paned)
        video_paned.add(self.video_panel, weight=7)
        
        # Bottom part: Grid display (30% of height)
        self.grid_frame = ttk.Frame(video_paned, relief=tk.SUNKEN)
        video_paned.add(self.grid_frame, weight=3)
        
        # Create grid canvas in the bottom part
        self.grid_canvas = tk.Canvas(self.grid_frame, highlightthickness=0)
        self.grid_canvas.pack(fill=tk.BOTH, expand=True)

        # Rest of the method remains the same...
        # Control panel frame
        control_frame = ttk.Frame(paned, relief=tk.RAISED)
        control_frame.config(width=400)
        
        # Add scrollable frame for controls
        canvas = tk.Canvas(control_frame)
        scrollbar = ttk.Scrollbar(control_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Control Panel Header
        ttk.Label(scrollable_frame, text="Control Panel", font=("Arial", 12, "bold")).pack(pady=10)
        
        # Video controls
        video_group = ttk.LabelFrame(scrollable_frame, text="Video Controls")
        video_group.pack(pady=10, padx=10, fill="x")
        
        video_controls = ttk.Frame(video_group)
        video_controls.pack(pady=10)
        
        ttk.Button(video_controls, text="Play", command=self.play_video).pack(side=tk.LEFT, padx=5)
        ttk.Button(video_controls, text="Pause", command=self.pause_video).pack(side=tk.LEFT, padx=5)
        ttk.Button(video_controls, text="Stop", command=self.stop_video).pack(side=tk.LEFT, padx=5)
        
        # Reload button for debugging
        ttk.Button(video_group, text="Reload Video", command=self.reload_video).pack(pady=5)
        
        # Audio controls
        audio_group = ttk.LabelFrame(scrollable_frame, text="Audio Controls")
        audio_group.pack(pady=10, padx=10, fill="x")
        
        ttk.Checkbutton(audio_group, text="Enable Audio Generation", 
                       variable=self.audio_enabled_var, command=self.toggle_audio).pack(pady=5)
        
        soundfont_frame = ttk.Frame(audio_group)
        soundfont_frame.pack(pady=5, fill="x")
        ttk.Button(soundfont_frame, text="Select Soundfont", command=self.select_soundfont).pack(side=tk.LEFT, padx=5)
        self.soundfont_label = ttk.Label(soundfont_frame, text="No soundfont selected")
        self.soundfont_label.pack(side=tk.LEFT, padx=5)
        
        # Grid settings
        grid_group = ttk.LabelFrame(scrollable_frame, text="Grid Settings")
        grid_group.pack(pady=10, padx=10, fill="x")
        
        # Grid size
        grid_size_frame = ttk.Frame(grid_group)
        grid_size_frame.pack(pady=5, fill="x")
        ttk.Label(grid_size_frame, text="Grid Size:").pack(side=tk.LEFT)
        
        self.grid_width_var = tk.StringVar(value=str(self.grid_width))
        self.grid_height_var = tk.StringVar(value=str(self.grid_height))
        
        ttk.Label(grid_size_frame, text="Width:").pack(side=tk.LEFT, padx=(10, 0))
        width_spinbox = ttk.Spinbox(grid_size_frame, from_=1, to=50, width=5, textvariable=self.grid_width_var, command=self.update_grid_settings)
        width_spinbox.pack(side=tk.LEFT, padx=5)

        ttk.Label(grid_size_frame, text="Height:").pack(side=tk.LEFT, padx=(10, 0))
        height_spinbox = ttk.Spinbox(grid_size_frame, from_=1, to=50, width=5, textvariable=self.grid_height_var, command=self.update_grid_settings)
        height_spinbox.pack(side=tk.LEFT, padx=5)
                
        # Note range
        note_range_frame = ttk.Frame(grid_group)
        note_range_frame.pack(pady=5, fill="x")
        ttk.Label(note_range_frame, text="Note Range:").pack(side=tk.LEFT)
        
        self.min_note_var = tk.StringVar(value=str(self.note_range[0]))
        self.max_note_var = tk.StringVar(value=str(self.note_range[1]))
        
        ttk.Label(note_range_frame, text="Min:").pack(side=tk.LEFT, padx=(10, 0))
        min_spinbox = ttk.Spinbox(note_range_frame, from_=0, to=127, width=5, textvariable=self.min_note_var, command=self.update_grid_settings)
        min_spinbox.pack(side=tk.LEFT, padx=5)

        ttk.Label(note_range_frame, text="Max:").pack(side=tk.LEFT, padx=(10, 0))
        max_spinbox = ttk.Spinbox(note_range_frame, from_=0, to=127, width=5, textvariable=self.max_note_var, command=self.update_grid_settings)
        max_spinbox.pack(side=tk.LEFT, padx=5)

        self.grid_width_var.trace('w', lambda name, index, mode: self.update_grid_settings())
        self.grid_height_var.trace('w', lambda name, index, mode: self.update_grid_settings())
        self.min_note_var.trace('w', lambda name, index, mode: self.update_grid_settings())
        self.max_note_var.trace('w', lambda name, index, mode: self.update_grid_settings())
        
        # Display settings
        display_group = ttk.LabelFrame(scrollable_frame, text="Display Settings")
        display_group.pack(pady=10, padx=10, fill="x")
        
        # Status info
        status_group = ttk.LabelFrame(scrollable_frame, text="Status")
        status_group.pack(pady=10, padx=10, fill="x")
        
        self.audio_status_label = ttk.Label(status_group, text="Audio: Disabled")
        self.audio_status_label.pack(pady=2)
        
        self.grid_info_label = ttk.Label(status_group, text=f"Grid: {self.grid_width}x{self.grid_height}")
        self.grid_info_label.pack(pady=2)
        
        self.notes_info_label = ttk.Label(status_group, text=f"Notes: {self.note_range[0]}-{self.note_range[1]}")
        self.notes_info_label.pack(pady=2)
        
        paned.add(control_frame, weight=1)

        # Initialize VLC after frame is created and mapped
        self.video_frame.bind("<Map>", self._init_vlc)

    def _create_status_bar(self):
        status_bar = ttk.Frame(self, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_msg = ttk.Label(status_bar, text="Ready")
        self.status_msg.pack(side=tk.LEFT, padx=5)
        self.stats_lbl = ttk.Label(status_bar, text="Time: --s | FPS: --")
        self.stats_lbl.pack(side=tk.RIGHT, padx=5)

    def _init_audio_generator(self):
        """Initialize the audio generator."""
        try:
            self.audio_generator = AudioGenerator(
                grid_width=self.grid_width,
                grid_height=self.grid_height,
                note_range=self.note_range,
                soundfont_path=self.current_soundfont
            )
            self.audio_status_label.config(text="Audio: Initialized")
        except Exception as e:
            print(f"Audio generator initialization error: {e}")
            self.audio_status_label.config(text="Audio: Error")
            messagebox.showerror("Audio Error", f"Failed to initialize audio system:\n{e}")

    def _on_frame_configure(self, event):
        # Could be used if resizing video window changes VLC viewport
        pass

    def _menu_action(self):
        # Placeholder
        pass

    def _init_vlc(self, event=None):
        """Initialize VLC manager only once and when frame is ready."""
        if not self.vlc_manager:
            try:
                # Ensure the frame is fully mapped before initializing VLC
                self.video_frame.update_idletasks()
                self.vlc_manager = VideoManager(self.video_panel, frame_callback=self._process_frame)
                print("VLC initialized successfully")
                
                # Rebind window handle on resize
                self.video_frame.bind("<Configure>", self._on_frame_configure)
                
            except Exception as e:
                print(f"VLC initialization failed: {e}")
                self.status_msg.config(text=f"VLC Error: {e}")

    def _process_frame(self, frame):
        """Process video frame for audio generation."""
        if not self.audio_enabled or not self.audio_generator or frame is None:
            return
            
        try:
            # Process frame through audio generator
            self.audio_generator.process_frame(frame)
        except Exception as e:
            print(f"Frame processing error: {e}")

    def _start_frame_processing(self):
        """Start frame processing thread for audio generation."""
        if self.frame_processing_thread is not None:
            return
            
        self.stop_frame_processing = False
        self.frame_processing_thread = threading.Thread(target=self._frame_processing_loop, daemon=True)
        self.frame_processing_thread.start()

    def _stop_frame_processing(self):
        """Stop frame processing thread."""
        self.stop_frame_processing = True
        if self.frame_processing_thread:
            self.frame_processing_thread.join(timeout=1.0)
            self.frame_processing_thread = None

    def _frame_processing_loop(self):
        """Main frame processing loop."""
        while not self.stop_frame_processing:
            try:
                if (self.audio_enabled and self.audio_generator and 
                    self.vlc_manager and self.vlc_manager.is_playing() and 
                    self.current_video_path):
                    
                    # Get current frame from video file
                    frame = self.vlc_manager.get_current_frame_from_file(self.current_video_path)
                    
                    if frame is not None:
                        # Process frame for audio
                        self.audio_generator.process_frame(frame)
                
                time.sleep(1/30)  # ~30 FPS processing
                
            except Exception as e:
                print(f"Frame processing loop error: {e}")
                time.sleep(0.1)

    def open_video(self):
        path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[("Video Files", "*.mp4 *.mov *.avi *.mkv *.wmv *.flv *.webm"), ("All Files", "*")]
        )
        if not path:
            return

        self.current_video_path = path
        self._load_video(path)

    def _load_video(self, path):
        """Load video with proper error handling."""
        try:
            # Stop frame processing
            self._stop_frame_processing()
            
            # Ensure VLC is initialized
            if not self.vlc_manager:
                self._init_vlc()
                
            if not self.vlc_manager:
                raise RuntimeError("VLC manager not initialized")

            # Stop any current video
            self.stop_video()

            # Load new video
            self.vlc_manager.open(path)

            self.vlc_manager.set_video_path(path)
            
            # Give VLC a moment to load the media
            self.after(500, lambda: self._start_video_playback(path))
            
        except Exception as e:
            print(f"Video loading error: {e}")
            self.status_msg.config(text=f"Error loading video: {e}")
            messagebox.showerror("Video Error", f"Failed to load video:\n{e}")

    def _start_video_playback(self, path):
        """Start video playback after media is loaded."""
        try:
            self.vlc_manager.play()
            self.status_msg.config(text=f"Playing: {os.path.basename(path)}")
            
            # Start frame processing if audio is enabled
            if self.audio_enabled:
                self._start_frame_processing()
                
            self.after(100, self._update_stats)
        except Exception as e:
            print(f"Playback error: {e}")
            self.status_msg.config(text=f"Playback error: {e}")

    def reload_video(self):
        """Reload the current video - useful for debugging."""
        if self.current_video_path:
            print(f"Reloading video: {self.current_video_path}")
            self._load_video(self.current_video_path)

    def play_video(self):
        if self.vlc_manager:
            self.vlc_manager.play()
            if self.audio_enabled:
                self._start_frame_processing()
            self.after(100, self._update_stats)

    def pause_video(self):
        if self.vlc_manager:
            self.vlc_manager.pause()
            self._stop_frame_processing()
            if self.audio_generator:
                self.audio_generator.stop_all_notes()

    def stop_video(self):
        if self.vlc_manager:
            self.vlc_manager.stop()
            self._stop_frame_processing()
            if self.audio_generator:
                self.audio_generator.stop_all_notes()

    def toggle_audio(self):
        """Toggle audio generation on/off."""
        self.audio_enabled = self.audio_enabled_var.get()
        
        if self.audio_enabled:
            if not self.audio_generator:
                self._init_audio_generator()
            self.audio_status_label.config(text="Audio: Enabled")
            if self.vlc_manager and self.vlc_manager.is_playing():
                self._start_frame_processing()
        else:
            self.audio_status_label.config(text="Audio: Disabled")
            self._stop_frame_processing()
            if self.audio_generator:
                self.audio_generator.stop_all_notes()

    def select_soundfont(self):
        """Select a soundfont file."""
        path = filedialog.askopenfilename(
            title="Select Soundfont File",
            filetypes=[("Soundfont Files", "*.sf2"), ("All Files", "*")]
        )
        if not path:
            return
            
        self.current_soundfont = path
        self.soundfont_label.config(text=f"SF: {os.path.basename(path)}")
        
        if self.audio_generator:
            self.audio_generator.set_soundfont(path)

    def update_grid_settings(self):
        """Update grid and note range settings."""
        try:
            # Get new values
            new_width = int(self.grid_width_var.get())
            new_height = int(self.grid_height_var.get())
            new_min_note = int(self.min_note_var.get())
            new_max_note = int(self.max_note_var.get())
            
            # Validate values
            if new_width < 1 or new_width > 50:
                raise ValueError("Grid width must be between 1 and 8")
            if new_height < 1 or new_height > 50:
                raise ValueError("Grid height must be between 1 and 8")
            if new_min_note < 0 or new_min_note > 127:
                raise ValueError("Min note must be between 0 and 127")
            if new_max_note < 0 or new_max_note > 127:
                raise ValueError("Max note must be between 0 and 127")
            if new_min_note >= new_max_note:
                raise ValueError("Min note must be less than max note")
            
            # Update values
            self.grid_width = new_width
            self.grid_height = new_height
            self.note_range = (new_min_note, new_max_note)
            
            # Update audio generator
            if self.audio_generator:
                self.audio_generator.set_grid_size(new_width, new_height)
                self.audio_generator.set_note_range(new_min_note, new_max_note)
            
            # Update status labels
            self.grid_info_label.config(text=f"Grid: {self.grid_width}x{self.grid_height}")
            self.notes_info_label.config(text=f"Notes: {self.note_range[0]}-{self.note_range[1]}")
            
        except ValueError as e:
            messagebox.showerror("Invalid Settings", str(e))

    def _update_stats(self):
        if self.vlc_manager and self.vlc_manager.is_playing():
            t = self.vlc_manager.get_time()
            fps = self.vlc_manager.get_fps()
            self.stats_lbl.config(text=f"Time: {t:.1f}s | FPS: {fps:.1f}")
            self.after(100, self._update_stats)

    def _update_grid_overlay(self):
        """Re-draw grid lines and flashing notes on the grid Canvas."""

        # Clear previous drawings
        self.grid_canvas.delete("all")

        w = self.grid_canvas.winfo_width()
        h = self.grid_canvas.winfo_height()
        
        # Make sure we have valid dimensions
        if w <= 1 or h <= 1:
            self.after(100, self._update_grid_overlay)
            return
        
        gw, gh = self.grid_width, self.grid_height
        cell_w, cell_h = w//gw, h//gh

        # Draw grid lines
        for i in range(1, gw):
            x = i * cell_w
            self.grid_canvas.create_line(x, 0, x, h, fill='white', width=2)
        for j in range(1, gh):
            y = j * cell_h
            self.grid_canvas.create_line(0, y, w, y, fill='white', width=2)

        # Draw outer border
        self.grid_canvas.create_rectangle(0, 0, w, h, outline='white', width=2, fill='')

        # Flash any currently playing notes with velocity-based color
        if self.audio_generator:
            for region_index, note in self.audio_generator.note_map.items():
                if note in self.audio_generator.current_notes:
                    # Get the velocity for this note
                    velocity = self.audio_generator.current_notes[note]
                    
                    # Convert velocity (0-127) to color intensity (0-255)
                    intensity = int((velocity / 127.0) * 255)
                    
                    # Create pink color based on intensity (pale pink to bright pink)
                    # Pink is achieved by high red, varying green, and high blue
                    red = 255  # Always full red for pink
                    green = max(0, intensity)  # Minimum green for pale pink, increases with intensity
                    blue = 255  # Always full blue for pink
                    
                    color = f"#{red:02x}{green:02x}{blue:02x}"
                    outline_color = f"#{255:02x}{min(255, green + 30):02x}{255:02x}"  # Slightly brighter outline
                    
                    # Compute row/col
                    row = region_index // gw
                    col = region_index % gw
                    x1, y1 = col * cell_w, row * cell_h
                    x2, y2 = x1 + cell_w, y1 + cell_h
                    
                    # Draw a colored rectangle for active notes
                    self.grid_canvas.create_rectangle(
                        x1 + 2, y1 + 2, x2 - 2, y2 - 2,
                        fill=color, outline=outline_color, width=2
                    )
            
            # Draw note labels
            for region_index, note in self.audio_generator.note_map.items():
                row = region_index // gw
                col = region_index % gw
                x = col * cell_w + cell_w // 2
                y = row * cell_h + cell_h // 2
                
                # Determine text color based on note state
                if note in self.audio_generator.current_notes:
                    text_color = 'white'  # White text on pink background
                else:
                    text_color = '#888888'  # Dark grey text for inactive notes
                
                # Note number only (removed the "ON" status)
                self.grid_canvas.create_text(x, y, text=f"N{note}", 
                                        fill=text_color, font=('Arial', 10, 'bold'))

        # Schedule next update
        self.after(int(1000/30), self._update_grid_overlay)

    def cleanup(self):
        """Clean up resources."""
        try:
            self._stop_frame_processing()
            
            if self.audio_generator:
                self.audio_generator.cleanup()
                self.audio_generator = None
                
            if self.vlc_manager:
                self.vlc_manager.cleanup()
                self.vlc_manager = None
                
        except Exception as e:
            print(f"Cleanup error: {e}")

    def on_closing(self):
        print("Closing application...")
        self.cleanup()
        self.destroy()
