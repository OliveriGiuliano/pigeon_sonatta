import tkinter as tk
from tkinter import messagebox
import pygame.midi 

from audio import AudioGenerator 

from scales import get_note_names

from typing import Optional
from config import AudioConfig
from logger import StructuredLogger

logger = StructuredLogger.get_logger(__name__)

class MidiTrack:
    """Encapsulates all settings and state for a single MIDI track."""
    def __init__(self, track_id: int, midi_out: pygame.midi.Output):
        self.track_id = track_id
        self.midi_out = midi_out

        self.audio_config = AudioConfig()
        
        # Parameters
        self.grid_width = self.audio_config.DEFAULT_GRID_WIDTH
        self.grid_height = self.audio_config.DEFAULT_GRID_HEIGHT
        self.note_range = self.audio_config.DEFAULT_NOTE_RANGE
        self.sensitivity = self.audio_config.SENSITIVITY
        self.current_scale = self.audio_config.SCALE
        self.current_root_note = self.audio_config.ROOT_NOTE
        self.current_metric = self.audio_config.DEFAULT_METRIC
        self.audio_enabled = False

        # Tkinter variables for data binding
        self.grid_width_var = tk.StringVar(value=str(self.grid_width))
        self.grid_height_var = tk.StringVar(value=str(self.grid_height))
        self.min_note_var = tk.StringVar(value=str(self.note_range[0]))
        self.max_note_var = tk.StringVar(value=str(self.note_range[1]))
        self.sensitivity_var = tk.DoubleVar(value=self.sensitivity)
        self.scale_var = tk.StringVar(value=self.current_scale)
        self.root_note_var = tk.StringVar(value=get_note_names()[self.current_root_note - 60])
        self.metric_var = tk.StringVar(value=self.current_metric)
        self.audio_enabled_var = tk.BooleanVar(value=self.audio_enabled)
        
        self.audio_generator: Optional[AudioGenerator] = None
        self._init_audio_generator()

    def _init_audio_generator(self):
        """Initializes the audio generator for this track."""
        try:
            # Pass the shared midi_out object to the generator
            self.audio_generator = AudioGenerator(midi_out=self.midi_out)
            self.update_audio_generator_settings()
        except Exception as e:
            logger.error(f"Track {self.track_id} audio generator init error: {e}")
            messagebox.showerror("Audio Error", f"Failed to initialize audio for Track {self.track_id}:\n{e}")
            
    def update_audio_generator_settings(self):
        """Applies all current settings to the audio generator instance."""
        if not self.audio_generator:
            return
        self.audio_generator.set_grid_size(self.grid_width, self.grid_height)
        self.audio_generator.set_note_range(self.note_range[0], self.note_range[1])
        self.audio_generator.set_scale(self.current_scale, self.current_root_note)
        self.audio_generator.set_metric(self.current_metric)
        self.audio_generator.set_sensitivity(self.sensitivity)

    def cleanup(self):
        """Cleans up resources for this track."""
        if self.audio_generator:
            self.audio_generator.cleanup()
            self.audio_generator = None