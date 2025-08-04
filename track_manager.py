import tkinter as tk
from tkinter import messagebox

from scales import get_note_names

from typing import Optional
from logger import StructuredLogger
from tracks import MidiTrack

logger = StructuredLogger.get_logger(__name__)

class TrackManager:
    def __init__(self, parent_window, midi_out):
        self.track_notebook = None
        self.midi_out = midi_out
        self.grid_visualizer = None
        self.tracks = []
        self.active_track_index = -1
        self.next_track_id = 0
        self.update_timer = None
        self.ui_builder = None
        self.parent_window = parent_window

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
        
        tab_frame = self.ui_builder._create_track_tab(new_track)
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
        
        if self.grid_visualizer.grid_overlay_timer:
            self.parent_window.after_cancel(self.grid_visualizer.grid_overlay_timer)
        self.grid_visualizer.grid_overlay_timer = self.parent_window.after(50, self.grid_visualizer._update_grid_overlay)

    def on_track_selected(self, event=None):
        """Handles switching between track tabs."""
        if not self.track_notebook or not self.tracks:
            return
            
        try:
            new_index = self.track_notebook.index(self.track_notebook.select())
            if new_index != self.active_track_index:
                self.active_track_index = new_index
                if self.grid_visualizer.grid_overlay_timer:
                    self.parent_window.after_cancel(self.grid_visualizer.grid_overlay_timer)
                self.grid_visualizer.grid_overlay_timer = self.parent_window.after(0, self.grid_visualizer._update_grid_overlay)
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
            self.parent_window.after_cancel(self.update_timer)
        self.update_timer = self.parent_window.after(150, self.update_track_settings)  # 150ms delay

    def toggle_invert_metric(self, event=None):
        """Toggles metric inversion for the active track."""
        track = self.get_active_track()
        if not track: return
        
        track.invert_metric = track.invert_metric_var.get()
        if track.audio_generator:
            track.audio_generator.set_invert_metric(track.invert_metric)

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
                track.current_scale != new_scale or
                track.current_root_note != new_root_note_name
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
            
            self.grid_visualizer._update_grid_overlay()
            
        except (ValueError, tk.TclError) as e:
            logger.warning(f"Invalid track settings input: {e}")
        except Exception as e:
            logger.error(f"Error updating track settings: {e}")

    def _on_threshold_change(self, threshold_type, label_widget, *args):
        """Handle threshold slider changes for the active track."""
        track = self.get_active_track()
        if not track: 
            return
        
        if threshold_type == 'on':
            new_threshold = track.note_on_threshold_var.get()
            label_widget.config(text=f"{new_threshold:.2f}")
            
            if new_threshold != track.note_on_threshold:
                track.note_on_threshold = new_threshold
                if track.audio_generator:
                    track.audio_generator.config.NOTE_ON_THRESHOLD = new_threshold
        else:  # threshold_type == 'off'
            new_threshold = track.note_off_threshold_var.get()
            label_widget.config(text=f"{new_threshold:.2f}")
            
            if new_threshold != track.note_off_threshold:
                track.note_off_threshold = new_threshold
                if track.audio_generator:
                    track.audio_generator.config.NOTE_OFF_THRESHOLD = new_threshold



    def update_midi_output(self, new_midi_out):
        """Update MIDI output for all tracks."""
        self.midi_out = new_midi_out
        for track in self.tracks:
            track.midi_out = new_midi_out
            if track.audio_generator:
                track.audio_generator.midi_out = new_midi_out
                track.audio_generator.is_initialized = new_midi_out is not None

    def stop_all_tracks(self):
        """Stop audio generation on all tracks."""
        for track in self.tracks:
            if track.audio_generator:
                track.audio_generator.stop_all_notes()

    def cleanup(self):
        """Clean up all tracks."""
        for track in self.tracks:
            track.cleanup()
        self.tracks.clear()