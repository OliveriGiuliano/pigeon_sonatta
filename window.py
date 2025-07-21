import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import atexit
import os
import threading
import time

from video import VideoManager  
from audio import AudioGenerator 

from scales import get_available_scales, get_note_names

from typing import Optional
from config import UIConfig, AudioConfig, VideoConfig
from logger import StructuredLogger

logger = StructuredLogger.get_logger(__name__)

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Video-to-MIDI Generator")

        # Centralized configuration
        self.ui_config = UIConfig()
        self.audio_config = AudioConfig()
        self.video_config = VideoConfig()

        self.geometry(self.ui_config.WINDOW_GEOMETRY)

        self.video_manager: Optional[VideoManager] = None
        self.current_video_path: Optional[str] = None
        
        self.audio_generator: Optional[AudioGenerator] = None
        self.audio_enabled = False
        
        # Grid settings initialized from config
        self.grid_width = self.ui_config.DEFAULT_GRID_WIDTH
        self.grid_height = self.ui_config.DEFAULT_GRID_HEIGHT
        self.note_range = self.ui_config.DEFAULT_NOTE_RANGE
        
        # UI Variables
        self.audio_enabled_var = tk.BooleanVar(value=self.audio_enabled)
        self.current_scale = "Pentatonic Major"
        self.current_root_note = 60

        # Create UI
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

    def _create_main_layout(self) -> None:
        """Creates the main paned layout of the application."""
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        video_area = self._create_video_area(paned)
        control_panel = self._create_control_panel(paned)
        
        paned.add(video_area, weight=3)
        paned.add(control_panel, weight=1)

        # Initialize video after frame is created and mapped
        self.video_frame.bind("<Map>", self._init_video_manager)

    # In window.py, add the following new helper methods to the MainWindow class
    def _create_video_area(self, parent: ttk.Panedwindow) -> ttk.Frame:
        """Creates the frame containing the video panel and grid display."""
        self.video_frame = ttk.Frame(parent, relief=tk.SUNKEN)
        self.video_frame.config(width=500, height=400)
        self.video_frame.pack_propagate(False)
        
        video_paned = ttk.Panedwindow(self.video_frame, orient=tk.VERTICAL)
        video_paned.pack(fill=tk.BOTH, expand=True)
        
        self.video_panel = tk.Label(video_paned)
        video_paned.add(self.video_panel, weight=7)
        
        self.grid_frame = ttk.Frame(video_paned, relief=tk.SUNKEN)
        video_paned.add(self.grid_frame, weight=3)
        
        self.grid_canvas = tk.Canvas(self.grid_frame, highlightthickness=0)
        self.grid_canvas.pack(fill=tk.BOTH, expand=True)
        
        return self.video_frame

    def _create_control_panel(self, parent: ttk.Panedwindow) -> ttk.Frame:
        """Creates the scrollable control panel on the right."""
        control_frame = ttk.Frame(parent, relief=tk.RAISED, width=400)
        
        canvas = tk.Canvas(control_frame)
        scrollbar = ttk.Scrollbar(control_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        ttk.Label(scrollable_frame, text="Control Panel", font=("Arial", 12, "bold")).pack(pady=10)
        
        # Create control groups
        self._create_video_controls(scrollable_frame)
        self._create_audio_controls(scrollable_frame)
        self._create_grid_settings(scrollable_frame)
        self._create_status_info(scrollable_frame)
        
        return control_frame

    def _create_video_controls(self, parent: ttk.Frame) -> None:
        """Creates the video playback control buttons."""
        group = ttk.LabelFrame(parent, text="Video Controls")
        group.pack(pady=10, padx=10, fill="x")
        
        controls = ttk.Frame(group)
        controls.pack(pady=10)
        
        ttk.Button(controls, text="Play", command=self.play_video).pack(side=tk.LEFT, padx=5)
        ttk.Button(controls, text="Pause", command=self.pause_video).pack(side=tk.LEFT, padx=5)
        ttk.Button(controls, text="Stop", command=self.stop_video).pack(side=tk.LEFT, padx=5)
        ttk.Button(group, text="Reload Video", command=self.reload_video).pack(pady=5)

    def _create_audio_controls(self, parent: ttk.Frame) -> None:
        """Creates the audio generation control widgets."""
        group = ttk.LabelFrame(parent, text="Audio Controls")
        group.pack(pady=10, padx=10, fill="x")
        
        ttk.Checkbutton(group, text="Enable Audio Generation", 
                    variable=self.audio_enabled_var, command=self.toggle_audio).pack(pady=5)
        
        frame = ttk.Frame(group)
        frame.pack(pady=5, fill="x")

    def _create_status_bar(self):
        status_bar = ttk.Frame(self, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_msg = ttk.Label(status_bar, text="Ready")
        self.status_msg.pack(side=tk.LEFT, padx=5)
        self.stats_lbl = ttk.Label(status_bar, text="FPS: -- | Target FPS: -- | Latency: -- | Target Latency: --")
        self.stats_lbl.pack(side=tk.RIGHT, padx=5)

    def _create_status_info(self, parent: ttk.Frame) -> None:
        """Creates the status information display panel."""
        group = ttk.LabelFrame(parent, text="Status")
        group.pack(pady=10, padx=10, fill="x")
        
        self.audio_status_label = ttk.Label(group, text="Audio: Disabled")
        self.audio_status_label.pack(pady=2, anchor="w", padx=5)
        
        self.grid_info_label = ttk.Label(group, text=f"Grid: {self.grid_width}x{self.grid_height}")
        self.grid_info_label.pack(pady=2, anchor="w", padx=5)
        
        self.notes_info_label = ttk.Label(group, text=f"Notes: {self.note_range[0]}-{self.note_range[1]}")
        self.notes_info_label.pack(pady=2, anchor="w", padx=5)

        root_note_name = self.root_note_var.get() if hasattr(self, 'root_note_var') else 'C'
        self.scale_info_label = ttk.Label(group, text=f"Scale: {self.current_scale} ({root_note_name})")
        self.scale_info_label.pack(pady=2, anchor="w", padx=5)

    def _create_grid_settings(self, parent: ttk.Frame) -> None:
        """Creates the widgets for configuring the grid, note range, and scale."""
        group = ttk.LabelFrame(parent, text="Grid Settings")
        group.pack(pady=10, padx=10, fill="x")

        # --- Grid Size ---
        size_frame = ttk.Frame(group)
        size_frame.pack(pady=5, fill="x")
        ttk.Label(size_frame, text="Grid Size:").pack(side=tk.LEFT)
        self.grid_width_var = tk.StringVar(value=str(self.grid_width))
        self.grid_height_var = tk.StringVar(value=str(self.grid_height))
        
        ttk.Label(size_frame, text="Width:").pack(side=tk.LEFT, padx=(10, 0))
        width_spinbox = ttk.Spinbox(size_frame, from_=1, to=127, width=5, textvariable=self.grid_width_var)
        width_spinbox.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(size_frame, text="Height:").pack(side=tk.LEFT, padx=(10, 0))
        height_spinbox = ttk.Spinbox(size_frame, from_=1, to=127, width=5, textvariable=self.grid_height_var)
        height_spinbox.pack(side=tk.LEFT, padx=5)
        
        self.grid_width_var.trace_add('write', lambda *_: self.update_grid_settings())
        self.grid_height_var.trace_add('write', lambda *_: self.update_grid_settings())

        # --- Note Range ---
        note_frame = ttk.Frame(group)
        note_frame.pack(pady=5, fill="x")
        ttk.Label(note_frame, text="Note Range:").pack(side=tk.LEFT)
        self.min_note_var = tk.StringVar(value=str(self.note_range[0]))
        self.max_note_var = tk.StringVar(value=str(self.note_range[1]))
        
        ttk.Label(note_frame, text="Min:").pack(side=tk.LEFT, padx=(10, 0))
        min_spinbox = ttk.Spinbox(note_frame, from_=0, to=127, width=5, textvariable=self.min_note_var)
        min_spinbox.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(note_frame, text="Max:").pack(side=tk.LEFT, padx=(10, 0))
        max_spinbox = ttk.Spinbox(note_frame, from_=0, to=127, width=5, textvariable=self.max_note_var)
        max_spinbox.pack(side=tk.LEFT, padx=5)
        
        self.min_note_var.trace_add('write', lambda *_: self.update_grid_settings())
        self.max_note_var.trace_add('write', lambda *_: self.update_grid_settings())

        # --- Scale Settings ---
        scale_frame = ttk.Frame(group)
        scale_frame.pack(pady=5, fill="x")
        ttk.Label(scale_frame, text="Scale:").pack(side=tk.LEFT)
        self.scale_var = tk.StringVar(value=self.current_scale)
        scale_combo = ttk.Combobox(scale_frame, textvariable=self.scale_var, values=get_available_scales(), state="readonly", width=15)
        scale_combo.pack(side=tk.LEFT, padx=5)
        scale_combo.bind("<<ComboboxSelected>>", self.on_scale_change)

        ttk.Label(scale_frame, text="Root:").pack(side=tk.LEFT, padx=(10, 0))
        self.root_note_var = tk.StringVar(value="C")
        note_names = get_note_names()
        root_combo = ttk.Combobox(scale_frame, textvariable=self.root_note_var, values=note_names, state="readonly", width=5)
        root_combo.pack(side=tk.LEFT, padx=5)
        root_combo.bind("<<ComboboxSelected>>", self.on_root_note_change)

    def _init_audio_generator(self):
        """Initialize the audio generator."""
        try:
            self.audio_generator = AudioGenerator(
                grid_width=self.grid_width,
                grid_height=self.grid_height,
                note_range=self.note_range,
                scale_name=self.current_scale,
                root_note=self.current_root_note
            )
            self.audio_status_label.config(text="Audio: Initialized")
        except Exception as e:
            logger.error(f"Audio generator initialization error: {e}")
            self.audio_status_label.config(text="Audio: Error")
            messagebox.showerror("Audio Error", f"Failed to initialize audio system:\n{e}")

    def _on_frame_configure(self, event):
        # Could be used if resizing video window changes viewport
        pass

    def _menu_action(self):
        # Placeholder
        pass

    def _init_video_manager(self, event=None):
        """Initialize Video manager only once and when frame is ready."""
        if not self.video_manager:
            try:
                # Ensure the frame is fully mapped before initializing video
                self.video_frame.update_idletasks()
                self.video_manager = VideoManager(self.video_panel, frame_callback=self._process_frame)
                logger.info("Video manager initialized successfully")
                
                # Rebind window handle on resize
                self.video_frame.bind("<Configure>", self._on_frame_configure)
                
            except Exception as e:
                logger.error(f"Video initialization failed: {e}")
                self.status_msg.config(text=f"Video Error: {e}")

    def _process_frame(self, frame):
        """Process video frame for audio generation with error handling."""
        if not self.audio_enabled or not self.audio_generator or frame is None:
            return
            
        try:
            # Process frame through audio generator
            self.audio_generator.process_frame(frame)
        except Exception as e:
            logger.error(f"Frame processing error: {e}")

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
            # Ensure Video is initialized
            if not self.video_manager:
                self._init_video_manager()
                
            if not self.video_manager:
                raise RuntimeError("Video manager not initialized")

            # Stop any current video
            self.stop_video()

            # Load new video
            self.video_manager.open(path)
            
            # Give Video a moment to load the media
            self.after(500, lambda: self._start_video_playback(path))
            
        except Exception as e:
            logger.error(f"Video loading error: {e}")
            self.status_msg.config(text=f"Error loading video: {e}")
            messagebox.showerror("Video Error", f"Failed to load video:\n{e}")

    def _start_video_playback(self, path):
        """Start video playback after media is loaded."""
        try:
            self.video_manager.play()
            self.status_msg.config(text=f"Playing: {os.path.basename(path)}")
                
            self.after(100, self._update_stats)
            self.after(50, self._process_ui_updates)  # Add this line
        except Exception as e:
            logger.error(f"Playback error: {e}")
            self.status_msg.config(text=f"Playback error: {e}")

    def _process_ui_updates(self):
        """Process UI updates from video manager in main thread."""
        if self.video_manager:
            self.video_manager.process_ui_updates()
        
        # Schedule next update
        if self.video_manager and self.video_manager.is_playing():
            self.after(33, self._process_ui_updates)  # ~30 FPS UI updates
        else:
            self.after(100, self._process_ui_updates)  # Slower polling when not playing

    def reload_video(self):
        """Reload the current video - useful for debugging."""
        if self.current_video_path:
            logger.info(f"Reloading video: {self.current_video_path}")
            self._load_video(self.current_video_path)

    def play_video(self):
        if self.video_manager:
            self.video_manager.play()
            self.after(100, self._update_stats)

    def pause_video(self):
        if self.video_manager:
            self.video_manager.pause()
            if self.audio_generator:
                self.audio_generator.stop_all_notes()

    def stop_video(self):
        if self.video_manager:
            self.video_manager.stop()
            if self.audio_generator:
                self.audio_generator.stop_all_notes()
            self.stats_lbl.config(text="FPS: -- | Target FPS: -- | Latency: -- | Target Latency: --")

    def toggle_audio(self):
        """Toggle audio generation on/off."""
        self.audio_enabled = self.audio_enabled_var.get()
        
        if self.audio_enabled:
            if not self.audio_generator:
                self._init_audio_generator()
            self.audio_status_label.config(text="Audio: Enabled")
        else:
            self.audio_status_label.config(text="Audio: Disabled")
            if self.audio_generator:
                self.audio_generator.stop_all_notes()

    def update_grid_settings(self):
        """Update grid and note range settings."""
        try:
            # Get new values
            new_width = int(self.grid_width_var.get())
            new_height = int(self.grid_height_var.get())
            new_min_note = int(self.min_note_var.get())
            new_max_note = int(self.max_note_var.get())
            
            # Validate values
            if new_width < 1 or new_width > 127:
                raise ValueError("Grid width must be between 1 and 127")
            if new_height < 1 or new_height > 127:
                raise ValueError("Grid height must be between 1 and 127")
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
        if self.video_manager and self.video_manager.is_playing():
            video_fps = self.video_manager.get_fps()
            current_fps = self.video_manager.get_current_fps()
            latency_s = self.video_manager.get_latency()
            
            target_latency_s = (1.0 / video_fps) if video_fps > 0 else 0
            
            stats_text = (f"FPS: {current_fps:.1f} | "
                          f"Target FPS: {video_fps:.1f} | "
                          f"Latency: {latency_s * 1000:.2f}ms | "
                          f"Target Latency: <{target_latency_s * 1000:.2f}ms")

            self.stats_lbl.config(text=stats_text)
            
            # Schedule the next update
            self.after(500, self._update_stats)
        else:
            # If not playing, check again in a bit without resetting the label immediately,
            # allowing stats to persist during pause.
            self.after(500, self._update_stats)

    def _update_grid_overlay(self):
        """Re-draw grid lines and flashing notes on the grid Canvas."""
        
        # Reduce update frequency to 20 FPS instead of 30
        update_interval = int(1000/20)  # 50ms instead of 33ms

        # Clear previous drawings
        self.grid_canvas.delete("all")

        w = self.grid_canvas.winfo_width()
        h = self.grid_canvas.winfo_height()
        
        # Make sure we have valid dimensions
        if w <= 1 or h <= 1:
            self.after(update_interval, self._update_grid_overlay)
            return
        
        gw, gh = self.grid_width, self.grid_height
        cell_w, cell_h = w//gw, h//gh

        # Draw grid lines
        for i in range(1, gw):
            x = i * cell_w
            self.grid_canvas.create_line(x, 0, x, h, fill='white', width=1)
        for j in range(1, gh):
            y = j * cell_h
            self.grid_canvas.create_line(0, y, w, y, fill='white', width=1)

        # Draw outer border
        self.grid_canvas.create_rectangle(0, 0, w, h, outline='white', width=2, fill='')

        # Only update active notes if audio generator exists - now thread-safe
        if self.audio_generator:
            self._draw_active_notes(gw, gh, cell_w, cell_h)

        # Schedule next update with reduced frequency
        self.after(update_interval, self._update_grid_overlay)

    def _draw_active_notes(self, gw, gh, cell_w, cell_h):
        """Draw active notes separately to optimize performance."""
        # Get thread-safe snapshot of current notes
        if not self.audio_generator:
            return
            
        current_notes_snapshot = self.audio_generator.get_current_notes_snapshot()
        note_map_copy = {}
        
        # Get thread-safe copy of note map
        with self.audio_generator.state_lock:
            note_map_copy = self.audio_generator.note_map.copy()
        
        for region_index, note in note_map_copy.items():
            if note in current_notes_snapshot:
                # Get the velocity for this note
                velocity = current_notes_snapshot[note]
                
                # Simplified color calculation
                intensity = min(255, velocity * 2)  # Scale 0-127 to 0-254, cap at 255
                color = f"#{255:02x}{intensity:02x}{255:02x}"
                
                # Compute row/col
                row = region_index // gw
                col = region_index % gw
                x1, y1 = col * cell_w, row * cell_h
                x2, y2 = x1 + cell_w, y1 + cell_h
                
                # Draw colored rectangle
                self.grid_canvas.create_rectangle(
                    x1 + 1, y1 + 1, x2 - 1, y2 - 1,
                    fill=color, outline='', width=0  # No outline for performance
                )
                
                # Draw note label
                x = col * cell_w + cell_w // 2
                y = row * cell_h + cell_h // 2
                self.grid_canvas.create_text(x, y, text=f"N{note}", 
                                        fill='white', font=('Arial', 8))  # Smaller font

    def on_scale_change(self, event=None):
        """Handle scale selection change."""
        self.current_scale = self.scale_var.get()
        self.update_scale_settings()

    def on_root_note_change(self, event=None):
        """Handle root note selection change."""
        note_name = self.root_note_var.get()
        note_names = get_note_names()
        if note_name in note_names:
            # Convert note name to MIDI note number (C4 = 60)
            self.current_root_note = 60 + note_names.index(note_name)
        self.update_scale_settings()

    def update_scale_settings(self):
        """Update scale settings in audio generator."""
        if self.audio_generator:
            self.audio_generator.set_scale(self.current_scale, self.current_root_note)
        
        # Update status label
        root_name = self.root_note_var.get() if hasattr(self, 'root_note_var') else 'C'
        self.scale_info_label.config(text=f"Scale: {self.current_scale} ({root_name})")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with guaranteed cleanup."""
        self.cleanup()
        return False

    def cleanup(self):
        """Clean up resources with proper error handling."""
        cleanup_errors = []
        
        try:
            # Clean up audio generator
            if self.audio_generator:
                try:
                    self.audio_generator.cleanup()
                except Exception as e:
                    cleanup_errors.append(f"Audio cleanup error: {e}")
                finally:
                    self.audio_generator = None
                    
            # Clean up video manager
            if self.video_manager:
                try:
                    self.video_manager.cleanup()
                except Exception as e:
                    cleanup_errors.append(f"Video cleanup error: {e}")
                finally:
                    self.video_manager = None
                    
            if cleanup_errors:
                logger.error(f"Cleanup completed with errors: {'; '.join(cleanup_errors)}")
            else:
                logger.info("Cleanup completed successfully")
                
        except Exception as e:
            logger.error(f"Critical cleanup error: {e}")

    def on_closing(self):
        logger.info("Closing application...")
        self.cleanup()
        self.destroy()
