import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import atexit
import os
import time

import pygame.midi 
import pygame.mixer 

from video import VideoManager  
from audio import AudioGenerator 

from scales import get_available_scales, get_note_names

from typing import Optional
from config import UIConfig, AudioConfig, VideoConfig
from logger import StructuredLogger
from tracks import MidiTrack

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

        self.tracks: list[MidiTrack] = []
        self.track_notebook: Optional[ttk.Notebook] = None
        self.active_track_index: int = -1
        self.next_track_id = 0
        self.midi_out: Optional[pygame.midi.Output] = None 
        
        self.update_timer = None
        self.grid_overlay_timer = None

        self.current_camera_index = None  # Track active camera

        self._initialize_global_audio() # Initialize audio systems once

        # Create UI
        self._create_menu()
        self._create_main_layout()
        self._create_status_bar()

        self._update_grid_overlay()
        
        self.add_track() # Add the first initial track

        # Register cleanup
        atexit.register(self.cleanup)

    def _initialize_global_audio(self):
        """Initializes global Pygame systems and the single MIDI output stream."""
        try:
            pygame.mixer.pre_init(
                frequency=self.audio_config.DEFAULT_FREQUENCY,
                size=-16,
                channels=2,
                buffer=self.audio_config.BUFFER_SIZE
            )
            pygame.mixer.init()
            pygame.midi.init()
            
            midi_device_id = pygame.midi.get_default_output_id()
            if midi_device_id == -1:
                logger.warning("No default MIDI output device found.")
                messagebox.showwarning("MIDI Error", "No default MIDI output device was found. Audio generation will be disabled.")
                return
                
            self.midi_out = pygame.midi.Output(midi_device_id)
            logger.info(f"Successfully initialized shared MIDI output on device ID {midi_device_id}.")
            
        except Exception as e:
            logger.error(f"Global audio initialization error: {e}", exc_info=True)
            messagebox.showerror("Audio Error", f"A critical error occurred initializing the audio system:\n{e}")

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
        input_menu.add_command(label="Camera", command=self.open_camera)
        input_menu.add_command(label="Input Settings", command=self._menu_action)
        menubar.add_cascade(label="Input", menu=input_menu)
        
        # Output menu
        output_menu = tk.Menu(menubar, tearoff=0)
        output_menu.add_command(label="Virtual MIDI Port", command=self._menu_action)
        output_menu.add_command(label="Save MIDI File", command=self._menu_action)
        output_menu.add_command(label="Record MIDI", command=self._menu_action)
        output_menu.add_separator()
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
        """Creates the main control panel area with track management."""
        control_area_frame = ttk.Frame(parent, relief=tk.RAISED, width=400)
        
        # --- Global Video Controls ---
        self._create_video_controls(control_area_frame)
        
        # --- Separator ---
        ttk.Separator(control_area_frame, orient='horizontal').pack(pady=10, fill='x', padx=10)
        
        # --- Track Management Buttons ---
        track_mgmt_frame = ttk.Frame(control_area_frame)
        track_mgmt_frame.pack(pady=5, padx=10, fill='x')
        
        ttk.Label(track_mgmt_frame, text="MIDI Tracks", font=("Arial", 12, "bold")).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(track_mgmt_frame, text="Add Track", command=self.add_track).pack(side=tk.LEFT, padx=5)
        ttk.Button(track_mgmt_frame, text="Remove Track", command=self.remove_track).pack(side=tk.LEFT, padx=5)

        # --- Track Notebook ---
        self.track_notebook = ttk.Notebook(control_area_frame)
        self.track_notebook.pack(pady=5, padx=10, fill="both", expand=True)
        self.track_notebook.bind("<<NotebookTabChanged>>", self.on_track_selected)
        
        return control_area_frame

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

    def on_metric_change(self, event=None):
        """Handle metric selection change."""
        self.current_metric = self.metric_var.get()
        
        # Update audio generator
        if self.audio_generator:
            self.audio_generator.set_metric(self.current_metric)
        
    def _on_sensitivity_change(self, *args):
        """Handle sensitivity slider change."""
        self.sensitivity = self.sensitivity_var.get()
        self.sensitivity_label.config(text=f"{self.sensitivity:.1f}")
        
        # Update audio generator sensitivity
        if self.audio_generator:
            self.audio_generator.set_sensitivity(self.sensitivity)

    def _create_status_bar(self):
        status_bar = ttk.Frame(self, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_msg = ttk.Label(status_bar, text="Ready")
        self.status_msg.pack(side=tk.LEFT, padx=5)
        self.stats_lbl = ttk.Label(status_bar, text="FPS: -- | Target FPS: -- | Latency: -- | Target Latency: --")
        self.stats_lbl.pack(side=tk.RIGHT, padx=5)

    def _create_audio_controls(self, parent: ttk.Frame, track: MidiTrack) -> None:
        """Creates the audio generation control widgets for a specific track."""
        group = ttk.LabelFrame(parent, text="Audio Controls")
        group.pack(pady=10, padx=10, fill="x")
        
        ttk.Checkbutton(group, text="Enable Audio Generation", 
                    variable=track.audio_enabled_var, command=self.toggle_track_audio).pack(pady=5)
        
        metric_frame = ttk.Frame(group)
        metric_frame.pack(pady=5, fill="x")
        ttk.Label(metric_frame, text="Metric:").pack(side=tk.LEFT)
        metric_combo = ttk.Combobox(metric_frame, textvariable=track.metric_var, 
                                values=self.audio_config.AVAILABLE_METRICS, 
                                state="readonly", width=15)
        metric_combo.pack(side=tk.LEFT, padx=5)
        metric_combo.bind("<<ComboboxSelected>>", self.on_metric_change)
        
        sens_frame = ttk.Frame(group)
        sens_frame.pack(pady=5, fill="x")
        ttk.Label(sens_frame, text="Sensitivity:").pack(side=tk.LEFT)
        sensitivity_scale = ttk.Scale(sens_frame, from_=0.0, to=10.0, 
                                    variable=track.sensitivity_var, 
                                    orient=tk.HORIZONTAL, length=150)
        sensitivity_scale.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
        sensitivity_label = ttk.Label(sens_frame, text=f"{track.sensitivity:.1f}")
        sensitivity_label.pack(side=tk.LEFT, padx=5)
        track.sensitivity_var.trace_add('write', lambda *args, label=sensitivity_label: self._on_sensitivity_change(label, *args))

        note_frame = ttk.Frame(group)
        note_frame.pack(pady=5, fill="x")
        ttk.Label(note_frame, text="Note Range:").pack(side=tk.LEFT)
        ttk.Label(note_frame, text="Min:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Spinbox(note_frame, from_=0, to=127, width=5, textvariable=track.min_note_var).pack(side=tk.LEFT, padx=5)
        ttk.Label(note_frame, text="Max:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Spinbox(note_frame, from_=0, to=127, width=5, textvariable=track.max_note_var).pack(side=tk.LEFT, padx=5)
        track.min_note_var.trace_add('write', lambda *_: self._debounced_update_track_settings())
        track.max_note_var.trace_add('write', lambda *_: self._debounced_update_track_settings())

        scale_frame = ttk.Frame(group)
        scale_frame.pack(pady=5, fill="x")
        ttk.Label(scale_frame, text="Scale:").pack(side=tk.LEFT)
        scale_combo = ttk.Combobox(scale_frame, textvariable=track.scale_var, values=get_available_scales(), state="readonly", width=15)
        scale_combo.pack(side=tk.LEFT, padx=5)
        scale_combo.bind("<<ComboboxSelected>>", self.on_scale_change)
        ttk.Label(scale_frame, text="Root:").pack(side=tk.LEFT, padx=(10, 0))
        root_combo = ttk.Combobox(scale_frame, textvariable=track.root_note_var, values=get_note_names(), state="readonly", width=5)
        root_combo.pack(side=tk.LEFT, padx=5)
        root_combo.bind("<<ComboboxSelected>>", self.on_root_note_change)

    def _create_grid_settings(self, parent: ttk.Frame, track: MidiTrack) -> None:
        """Creates the widgets for configuring the grid for a specific track."""
        group = ttk.LabelFrame(parent, text="Grid Settings")
        group.pack(pady=10, padx=10, fill="x")

        size_frame = ttk.Frame(group)
        size_frame.pack(pady=5, fill="x")
        ttk.Label(size_frame, text="Grid Size:").pack(side=tk.LEFT)
        ttk.Label(size_frame, text="Width:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Spinbox(size_frame, from_=1, to=127, width=5, textvariable=track.grid_width_var).pack(side=tk.LEFT, padx=5)
        ttk.Label(size_frame, text="Height:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Spinbox(size_frame, from_=1, to=127, width=5, textvariable=track.grid_height_var).pack(side=tk.LEFT, padx=5)
        
        track.grid_width_var.trace_add('write', lambda *_: self._debounced_update_track_settings())
        track.grid_height_var.trace_add('write', lambda *_: self._debounced_update_track_settings())

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
        """Process video frame for audio generation across all enabled tracks."""
        if frame is None:
            return
            
        try:
            for track in self.tracks:
                if track.audio_enabled and track.audio_generator:
                    track.audio_generator.process_frame(frame)
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
            
            self.current_camera_index = None  # Clear camera index

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
            self.after(50, self._process_ui_updates)
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
        """Reloads current video or camera source."""
        if self.current_video_path:
            self._load_video(self.current_video_path)
        elif self.current_camera_index is not None:
            self._load_camera(self.current_camera_index)
        else:
            logger.info("No video or camera to reload")

    def play_video(self):
        if self.video_manager:
            self.video_manager.play()
            self.after(100, self._update_stats)

    def pause_video(self):
        if self.video_manager:
            self.video_manager.pause()
            for track in self.tracks:
                if track.audio_generator:
                    track.audio_generator.stop_all_notes()

    def stop_video(self):
        if self.video_manager:
            self.video_manager.stop()
            for track in self.tracks:
                if track.audio_generator:
                    track.audio_generator.stop_all_notes()
            self.stats_lbl.config(text="FPS: -- | Target FPS: -- | Latency: -- | Target Latency: --")

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
        """Re-draw grid lines and flashing notes for the active track."""
        if self.grid_overlay_timer:
            self.after_cancel(self.grid_overlay_timer)
            self.grid_overlay_timer = None
     
        start_time = time.time()
        update_interval = 50  # ms
        
        self.grid_canvas.delete("all")

        w = self.grid_canvas.winfo_width()
        h = self.grid_canvas.winfo_height()
        active_track = self.get_active_track()
        
        if not active_track or w <= 1 or h <= 1:
            self.after(update_interval, self._update_grid_overlay)
            return
        
        gw, gh = active_track.grid_width, active_track.grid_height
        cell_w, cell_h = w//gw, h//gh

        for i in range(1, gw):
            x = i * cell_w
            self.grid_canvas.create_line(x, 0, x, h, fill='white', width=1)
        for j in range(1, gh):
            y = j * cell_h
            self.grid_canvas.create_line(0, y, w, y, fill='white', width=1)

        self.grid_canvas.create_rectangle(0, 0, w, h, outline='white', width=2, fill='')

        if active_track.audio_generator:
            self._draw_active_notes(active_track.audio_generator, gw, gh, cell_w, cell_h)

        self.grid_overlay_timer = self.after(update_interval, self._update_grid_overlay)

    def _draw_active_notes(self, audio_generator: AudioGenerator, gw, gh, cell_w, cell_h):
        """Draw active notes for a specific audio generator."""
        if not audio_generator:
            return
            
        current_notes_snapshot = audio_generator.get_current_notes_snapshot()
        note_map_copy = {}
        
        with audio_generator.state_lock:
            note_map_copy = audio_generator.note_map.copy()
        
        for region_index, note in note_map_copy.items():
            if note in current_notes_snapshot:
                velocity = current_notes_snapshot[note]
                intensity = 255 - min(255, velocity * 2)
                color = f"#{255:02x}{intensity:02x}{255:02x}"
                
                row, col = divmod(region_index, gw)
                x1, y1 = col * cell_w, row * cell_h
                x2, y2 = x1 + cell_w, y1 + cell_h
                
                self.grid_canvas.create_rectangle(x1 + 1, y1 + 1, x2 - 1, y2 - 1, fill=color, outline='', width=0)
                
                x_text, y_text = x1 + cell_w // 2, y1 + cell_h // 2
                self.grid_canvas.create_text(x_text, y_text, text=f"N{note}", fill='white', font=('Arial', 8))

    def _create_track_tab(self, track: MidiTrack) -> ttk.Frame:
        """Creates a new tab for a given track with all its controls."""
        tab_frame = ttk.Frame(self.track_notebook)
        
        canvas = tk.Canvas(tab_frame)
        scrollbar = ttk.Scrollbar(tab_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Create control groups for this specific track
        self._create_audio_controls(scrollable_frame, track)
        self._create_grid_settings(scrollable_frame, track)
        
        return tab_frame

    def add_track(self):
        """Adds a new MIDI track and its corresponding UI tab."""
        # Ensure we have a valid MIDI output before adding a track
        if self.midi_out is None:
            messagebox.showerror("MIDI Error", "Cannot add a track because the MIDI output is not available.")
            return
            
        track_id = self.next_track_id
        # Pass the shared midi_out object to the new track
        new_track = MidiTrack(track_id=track_id, midi_out=self.midi_out)
        self.tracks.append(new_track)
        self.next_track_id += 1
        
        tab_frame = self._create_track_tab(new_track)
        self.track_notebook.add(tab_frame, text=f"Track {track_id + 1}")
        
        self.track_notebook.select(len(self.tracks) - 1)
        
        logger.info(f"Added Track {track_id + 1}")

    def remove_track(self):
        """Removes the currently selected MIDI track."""
        if len(self.tracks) <= 1:
            messagebox.showwarning("Remove Track", "Cannot remove the last track.")
            return

        selected_index = self.track_notebook.index(self.track_notebook.select())
        track_to_remove = self.tracks[selected_index]
        logger.info(f"Removing Track {track_to_remove.track_id + 1}")
        
        track_to_remove.cleanup()
        self.tracks.pop(selected_index)
        self.track_notebook.forget(selected_index)
        
        if self.grid_overlay_timer:
            self.after_cancel(self.grid_overlay_timer)
        self.grid_overlay_timer = self.after(50, self._update_grid_overlay)

    def on_track_selected(self, event=None):
        """Handles switching between track tabs."""
        if not self.track_notebook or not self.tracks:
            return
            
        try:
            new_index = self.track_notebook.index(self.track_notebook.select())
            if new_index != self.active_track_index:
                self.active_track_index = new_index
                if self.grid_overlay_timer:
                    self.after_cancel(self.grid_overlay_timer)
                self.grid_overlay_timer = self.after(0, self._update_grid_overlay)
        except (tk.TclError, IndexError):
            self.active_track_index = -1

    def get_active_track(self) -> Optional[MidiTrack]:
        """Returns the currently active track, or None."""
        if self.active_track_index != -1 and self.active_track_index < len(self.tracks):
            return self.tracks[self.active_track_index]
        return None

    def toggle_track_audio(self, event=None):
        """Toggles audio generation for the active track."""
        track = self.get_active_track()
        if not track: return
        
        track.audio_enabled = track.audio_enabled_var.get()
        
        if not track.audio_enabled and track.audio_generator:
            track.audio_generator.stop_all_notes()

    def on_metric_change(self, event=None):
        """Handle metric selection change for the active track."""
        track = self.get_active_track()
        if not track: return
        
        new_metric = track.metric_var.get()
        if new_metric != track.current_metric:
            track.current_metric = new_metric
            if track.audio_generator:
                track.audio_generator.set_metric(track.current_metric)
            logger.info(f"Track {track.track_id + 1} metric set to {new_metric}")

    def _on_sensitivity_change(self, label_widget, *args):
        """Handle sensitivity slider change for the active track."""
        track = self.get_active_track()
        if not track: return
        
        new_sensitivity = track.sensitivity_var.get()
        label_widget.config(text=f"{new_sensitivity:.1f}")
        
        if new_sensitivity != track.sensitivity:
            track.sensitivity = new_sensitivity
            if track.audio_generator:
                track.audio_generator.set_sensitivity(track.sensitivity)

    def on_scale_change(self, event=None):
        self.update_track_settings()

    def on_root_note_change(self, event=None):
        self.update_track_settings()

    def _debounced_update_track_settings(self):
        """Debounced version of update_track_settings to prevent UI freezing from rapid changes."""
        if self.update_timer:
            self.after_cancel(self.update_timer)
        self.update_timer = self.after(150, self.update_track_settings)  # 150ms delay

    def update_track_settings(self):
        """Update all settings for the active track from its UI widgets."""
        self.update_timer = None  # Clear the timer reference
        track = self.get_active_track()
        if not track: return

        try:
            # Get values with bounds checking
            new_width = max(1, min(127, int(track.grid_width_var.get())))
            new_height = max(1, min(127, int(track.grid_height_var.get())))
            new_min_note = max(0, min(127, int(track.min_note_var.get())))
            new_max_note = max(0, min(127, int(track.max_note_var.get())))
            
            # Ensure min < max
            if new_min_note >= new_max_note:
                new_max_note = min(127, new_min_note + 1)
                track.max_note_var.set(new_max_note)
            
            new_scale = track.scale_var.get()
            new_root_note_name = track.root_note_var.get()

            # Only update if values actually changed
            settings_changed = (
                track.grid_width != new_width or
                track.grid_height != new_height or
                track.note_range != (new_min_note, new_max_note) or
                track.current_scale != new_scale
            )
            
            if not settings_changed:
                return
            
            track.grid_width = new_width
            track.grid_height = new_height
            track.note_range = (new_min_note, new_max_note)
            track.current_scale = new_scale
            
            note_names = get_note_names()
            if new_root_note_name in note_names:
                track.current_root_note = 60 + note_names.index(new_root_note_name)

            if track.audio_generator:
                track.update_audio_generator_settings()
            
            self._update_grid_overlay()
            
        except (ValueError, tk.TclError) as e:
            logger.warning(f"Invalid track settings input: {e}")
        except Exception as e:
            logger.error(f"Error updating track settings: {e}")

    def open_camera(self):
        """Opens a camera device for live video input."""
        camera_index = 0  # Default to first camera
        self.current_camera_index = camera_index
        self.current_video_path = None  # Clear video path
        
        try:
            self._load_camera(camera_index)
        except Exception as e:
            logger.error(f"Camera error: {e}")
            self.status_msg.config(text=f"Camera Error: {e}")
            messagebox.showerror("Camera Error", f"Failed to open camera:\n{e}")

    def _load_camera(self, camera_index):
        """Loads a camera device with proper error handling."""
        if not self.video_manager:
            self._init_video_manager()
            
        if not self.video_manager:
            raise RuntimeError("Video manager not initialized")

        self.stop_video()
        self.video_manager.open_camera(camera_index)
        
        # Start playback after initialization
        self.after(500, lambda: self._start_camera_playback(camera_index))

    def _start_camera_playback(self, camera_index):
        try:
            self.video_manager.play()
            self.status_msg.config(text=f"Camera {camera_index}")
            self.after(100, self._update_stats)
            self.after(50, self._process_ui_updates)
        except Exception as e:
            logger.error(f"Camera playback error: {e}")
            self.status_msg.config(text=f"Playback error: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with guaranteed cleanup."""
        self.cleanup()
        return False

    def cleanup(self):
        """Clean up resources with proper error handling."""
        if self.update_timer:
            self.after_cancel(self.update_timer)
            self.update_timer = None
        
        logger.info("Cleaning up all tracks and resources...")
        cleanup_errors = []
        
        for track in self.tracks:
            try:
                track.cleanup()
            except Exception as e:
                cleanup_errors.append(f"Track {track.track_id} cleanup error: {e}")
        self.tracks.clear()
                
        if self.video_manager:
            try:
                self.video_manager.cleanup()
            except Exception as e:
                cleanup_errors.append(f"Video cleanup error: {e}")
            finally:
                self.video_manager = None
                
        # After all individual components are cleaned, shut down global systems.
        if pygame.midi.get_init():
            pygame.midi.quit()
        if pygame.mixer.get_init():
            pygame.mixer.quit()

        if cleanup_errors:
            logger.error(f"Cleanup completed with errors: {'; '.join(cleanup_errors)}")
        else:
            logger.info("Cleanup completed successfully")

    def on_closing(self):
        logger.info("Closing application...")
        self.cleanup()
        self.destroy()
