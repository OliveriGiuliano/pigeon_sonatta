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

class UIBuilder:
    def __init__(self, parent_window, callbacks):
        self.callbacks = callbacks
        self.parent_window = parent_window

    def _create_menu(self):
        menubar = tk.Menu(self.parent_window)
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        for label in ["New Project", "Open Project", "Save Project", "Save Project As", None, "Exit"]:
            if label:
                file_menu.add_command(label=label, command=self.callbacks["_menu_action"])
            else:
                file_menu.add_separator()
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Input menu
        input_menu = tk.Menu(menubar, tearoff=0)
        input_menu.add_command(label="Video File", command=self.callbacks["open_video"])
        input_menu.add_command(label="Camera", command=self.callbacks["open_camera"])
        input_menu.add_command(label="Input Settings", command=self.callbacks["_menu_action"])
        menubar.add_cascade(label="Input", menu=input_menu)
        
        # Output menu
        output_menu = tk.Menu(menubar, tearoff=0)
        self.parent_window.midi_device_menu = tk.Menu(output_menu, tearoff=0)
        output_menu.add_cascade(label="Virtual MIDI Port", menu=self.parent_window.midi_device_menu)
        # Populate the menu
        self.callbacks["_populate_midi_devices"]()
        output_menu.add_command(label="Save MIDI File", command=self.callbacks["_menu_action"])
        output_menu.add_command(label="Record MIDI", command=self.callbacks["_menu_action"])
        output_menu.add_separator()
        output_menu.add_command(label="Audio Device", command=self.callbacks["_menu_action"])
        menubar.add_cascade(label="Output", menu=output_menu)
        
        # Presets menu
        presets_menu = tk.Menu(menubar, tearoff=0)
        presets_menu.add_command(label="Load Preset", command=self.callbacks["_menu_action"])
        presets_menu.add_command(label="Save Preset", command=self.callbacks["_menu_action"])
        presets_menu.add_command(label="Manage Presets", command=self.callbacks["_menu_action"])
        presets_menu.add_separator()
        presets_menu.add_command(label="Factory Reset", command=self.callbacks["_menu_action"])
        menubar.add_cascade(label="Presets", menu=presets_menu)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Show Visual Feedback", command=self.callbacks["_menu_action"])
        view_menu.add_command(label="Show Filter Preview", command=self.callbacks["_menu_action"])
        view_menu.add_command(label="Fullscreen Video", command=self.callbacks["_menu_action"])
        menubar.add_cascade(label="View", menu=view_menu)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.callbacks["_menu_action"])
        help_menu.add_command(label="Documentation", command=self.callbacks["_menu_action"])
        menubar.add_cascade(label="Help", menu=help_menu)

        self.parent_window.config(menu=menubar)

    def _create_main_layout(self) -> None:
        """Creates the main paned layout of the application."""
        paned = ttk.Panedwindow(self.parent_window, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        video_area = self._create_video_area(paned)
        control_panel = self._create_control_panel(paned)
        
        paned.add(video_area, weight=3)
        paned.add(control_panel, weight=1)

    def _create_video_area(self, parent: ttk.Panedwindow) -> ttk.Frame:
        """Creates the frame containing the video panel and grid display."""
        self.parent_window.video_frame = ttk.Frame(parent, relief=tk.SUNKEN)
        self.parent_window.video_frame.config(width=500, height=400)
        self.parent_window.video_frame.pack_propagate(False)
        
        video_paned = ttk.Panedwindow(self.parent_window.video_frame, orient=tk.VERTICAL)
        video_paned.pack(fill=tk.BOTH, expand=True)
        
        self.parent_window.video_panel = tk.Label(video_paned)
        video_paned.add(self.parent_window.video_panel, weight=7)
        
        self.parent_window.grid_frame = ttk.Frame(video_paned, relief=tk.SUNKEN)
        video_paned.add(self.parent_window.grid_frame, weight=3)
        
        self.parent_window.grid_canvas = tk.Canvas(self.parent_window.grid_frame, highlightthickness=0)
        self.parent_window.grid_canvas.pack(fill=tk.BOTH, expand=True)
        self.parent_window.grid_canvas.bind("<Button-1>", self.callbacks["_on_grid_click"])
        
        return self.parent_window.video_frame

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
        ttk.Button(track_mgmt_frame, text="Add Track", command=self.callbacks["add_track"]).pack(side=tk.LEFT, padx=5)
        ttk.Button(track_mgmt_frame, text="Remove Track", command=self.callbacks["remove_track"]).pack(side=tk.LEFT, padx=5)

        # --- Track Notebook ---
        self.parent_window.track_notebook = ttk.Notebook(control_area_frame)
        self.parent_window.track_notebook.pack(pady=5, padx=10, fill="both", expand=True)
        self.parent_window.track_notebook.bind("<<NotebookTabChanged>>", self.callbacks["on_track_selected"])
        
        return control_area_frame

    def _create_video_controls(self, parent: ttk.Frame) -> None:
        """Creates the video playback control buttons."""
        group = ttk.LabelFrame(parent, text="Video Controls")
        group.pack(pady=10, padx=10, fill="x")
        
        controls = ttk.Frame(group)
        controls.pack(pady=10)
        
        ttk.Button(controls, text="Play", command=self.callbacks["play_video"]).pack(side=tk.LEFT, padx=5)
        ttk.Button(controls, text="Pause", command=self.callbacks["pause_video"]).pack(side=tk.LEFT, padx=5)
        ttk.Button(controls, text="Stop", command=self.callbacks["stop_video"]).pack(side=tk.LEFT, padx=5)
        ttk.Button(group, text="Reload Video", command=self.callbacks["reload_video"]).pack(pady=5)

    def _create_status_bar(self):
        status_bar = ttk.Frame(self.parent_window, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.parent_window.status_msg = ttk.Label(status_bar, text="Ready")
        self.parent_window.status_msg.pack(side=tk.LEFT, padx=5)
        self.parent_window.stats_lbl = ttk.Label(status_bar, text="FPS: -- | Target FPS: -- | Latency: -- | Target Latency: --")
        self.parent_window.stats_lbl.pack(side=tk.RIGHT, padx=5)

    def _create_audio_controls(self, parent: ttk.Frame, track: MidiTrack) -> None:
        """Creates the audio generation control widgets for a specific track."""
        group = ttk.LabelFrame(parent, text="Audio Controls")
        group.pack(pady=10, padx=10, fill="x")
        
        ttk.Checkbutton(group, text="Enable Audio Generation", 
                    variable=track.audio_enabled_var, command=self.callbacks["toggle_track_audio"]).pack(pady=5)
        
        metric_frame = ttk.Frame(group)
        metric_frame.pack(pady=5, fill="x")
        ttk.Label(metric_frame, text="Metric:").pack(side=tk.LEFT)
        metric_combo = ttk.Combobox(metric_frame, textvariable=track.metric_var, 
                                values=self.parent_window.audio_config.AVAILABLE_METRICS, 
                                state="readonly", width=15)
        metric_combo.pack(side=tk.LEFT, padx=5)
        metric_combo.bind("<<ComboboxSelected>>", self.parent_window.on_metric_change)
        
        sens_frame = ttk.Frame(group)
        sens_frame.pack(pady=5, fill="x")
        ttk.Label(sens_frame, text="Sensitivity:").pack(side=tk.LEFT)
        sensitivity_scale = ttk.Scale(sens_frame, from_=0.0, to=10.0, 
                                    variable=track.sensitivity_var, 
                                    orient=tk.HORIZONTAL, length=150)
        sensitivity_scale.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
        sensitivity_label = ttk.Label(sens_frame, text=f"{track.sensitivity:.1f}")
        sensitivity_label.pack(side=tk.LEFT, padx=5)
        track.sensitivity_var.trace_add('write', lambda *args, label=sensitivity_label: self.callbacks["_on_sensitivity_change"](label, *args))

        ttk.Checkbutton(group, text="Invert Metric", 
                        variable=track.invert_metric_var, 
                        command=self.callbacks["toggle_invert_metric"]).pack(pady=5)

        threshold_frame = ttk.LabelFrame(group, text="Activation Thresholds")
        threshold_frame.pack(pady=5, fill="x")

        on_thresh_frame = ttk.Frame(threshold_frame)
        on_thresh_frame.pack(pady=2, fill="x")
        ttk.Label(on_thresh_frame, text="Note On:").pack(side=tk.LEFT)
        on_threshold_scale = ttk.Scale(on_thresh_frame, from_=0.0, to=1.0, 
                                    variable=track.note_on_threshold_var, 
                                    orient=tk.HORIZONTAL, length=120)
        on_threshold_scale.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
        on_threshold_label = ttk.Label(on_thresh_frame, text=f"{track.note_on_threshold:.2f}")
        on_threshold_label.pack(side=tk.LEFT, padx=5)
        track.note_on_threshold_var.trace_add('write', lambda *args, label=on_threshold_label: self.callbacks["_on_threshold_change"]('on', label, *args))

        off_thresh_frame = ttk.Frame(threshold_frame)
        off_thresh_frame.pack(pady=2, fill="x")
        ttk.Label(off_thresh_frame, text="Note Off:").pack(side=tk.LEFT)
        off_threshold_scale = ttk.Scale(off_thresh_frame, from_=0.0, to=1.0, 
                                    variable=track.note_off_threshold_var, 
                                    orient=tk.HORIZONTAL, length=120)
        off_threshold_scale.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
        off_threshold_label = ttk.Label(off_thresh_frame, text=f"{track.note_off_threshold:.2f}")
        off_threshold_label.pack(side=tk.LEFT, padx=5)
        track.note_off_threshold_var.trace_add('write', lambda *args, label=off_threshold_label: self.callbacks["_on_threshold_change"]('off', label, *args))

        note_frame = ttk.Frame(group)
        note_frame.pack(pady=5, fill="x")
        ttk.Label(note_frame, text="Note Range:").pack(side=tk.LEFT)
        ttk.Label(note_frame, text="Min:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Spinbox(note_frame, from_=0, to=127, width=5, textvariable=track.min_note_var).pack(side=tk.LEFT, padx=5)
        ttk.Label(note_frame, text="Max:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Spinbox(note_frame, from_=0, to=127, width=5, textvariable=track.max_note_var).pack(side=tk.LEFT, padx=5)
        track.min_note_var.trace_add('write', lambda *_: self.callbacks["_debounced_update_track_settings"]())
        track.max_note_var.trace_add('write', lambda *_: self.callbacks["_debounced_update_track_settings"]())

        scale_frame = ttk.Frame(group)
        scale_frame.pack(pady=5, fill="x")
        ttk.Label(scale_frame, text="Scale:").pack(side=tk.LEFT)
        scale_combo = ttk.Combobox(scale_frame, textvariable=track.scale_var, values=get_available_scales(), state="readonly", width=15)
        scale_combo.pack(side=tk.LEFT, padx=5)
        scale_combo.bind("<<ComboboxSelected>>", self.callbacks["on_scale_change"])
        ttk.Label(scale_frame, text="Root:").pack(side=tk.LEFT, padx=(10, 0))
        root_combo = ttk.Combobox(scale_frame, textvariable=track.root_note_var, values=get_note_names(), state="readonly", width=5)
        root_combo.pack(side=tk.LEFT, padx=5)
        root_combo.bind("<<ComboboxSelected>>", self.callbacks["on_root_note_change"])

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
        ttk.Button(size_frame, text="Reset custom notes", command=track.reset_custom_note_map).pack(side=tk.LEFT, padx=5)

        track.grid_width_var.trace_add('write', lambda *_: self.callbacks["_debounced_update_track_settings"]())
        track.grid_height_var.trace_add('write', lambda *_: self.callbacks["_debounced_update_track_settings"]())

    def _create_track_tab(self, track: MidiTrack) -> ttk.Frame:
        """Creates a new tab for a given track with all its controls."""
        tab_frame = ttk.Frame(self.parent_window.track_notebook)
        
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

    def build_menu(self):
        self._create_menu()
        self._create_main_layout()
        self._create_status_bar()