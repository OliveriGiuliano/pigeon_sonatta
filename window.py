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

from ui_builder import UIBuilder

logger = StructuredLogger.get_logger(__name__)

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Video-to-MIDI Generator")

        # Centralized configuration
        self.ui_config = UIConfig()
        self.audio_config = AudioConfig()
        self.video_config = VideoConfig()

        ui_callbacks = {"_menu_action":self._menu_action,
                        "open_video":self.open_video,
                        "open_camera":self.open_camera,
                        "_on_grid_click":self._on_grid_click,
                        "add_track":self.add_track,
                        "remove_track":self.remove_track,
                        "on_track_selected":self.on_track_selected,
                        "play_video":self.play_video,
                        "pause_video":self.pause_video,
                        "stop_video":self.stop_video,
                        "reload_video":self.reload_video,
                        "toggle_track_audio":self.toggle_track_audio,
                        "_on_sensitivity_change":self._on_sensitivity_change,
                        "toggle_invert_metric":self.toggle_invert_metric,
                        "_on_threshold_change":self._on_threshold_change,
                        "_debounced_update_track_settings":self._debounced_update_track_settings,
                        "on_root_note_change":self.on_root_note_change,
                        "_populate_midi_devices":self._populate_midi_devices,
                        "on_scale_change":self.on_scale_change
                        }

        self.ui_builder = UIBuilder(self, ui_callbacks)

        self.geometry(self.ui_config.WINDOW_GEOMETRY)

        self.video_manager: Optional[VideoManager] = None
        self.current_video_path: Optional[str] = None

        self.tracks: list[MidiTrack] = []
        self.track_notebook: Optional[ttk.Notebook] = None
        self.active_track_index: int = -1
        self.next_track_id = 0
        self.midi_out: Optional[pygame.midi.Output] = None 
        
        self.update_timer = None
        self.grid_overlay_timer_id = None

        self.current_camera_index = None  # Track active camera
        self.selected_midi_device_id = None

        self._initialize_global_audio() # Initialize audio systems once

        # Create UI
        self.ui_builder.build_menu()

        self._update_grid_overlay()
        
        self.add_track() # Add the first initial track

        self._update_stats() # start stat update loop
        self._process_ui_updates() # start ui update loop

    def _initialize_global_audio(self):
        """Initializes global Pygame systems and the single MIDI output stream."""
        try:
            # Shutdown existing MIDI to allow re-initialization
            if self.midi_out:
                self.midi_out.close()
                self.midi_out = None
            if pygame.midi.get_init():
                pygame.midi.quit()

            pygame.mixer.pre_init(
                frequency=self.audio_config.DEFAULT_FREQUENCY,
                size=-16,
                channels=2,
                buffer=self.audio_config.BUFFER_SIZE
            )
            pygame.mixer.init()
            pygame.midi.init()

            if not self.selected_midi_device_id:
                self.selected_midi_device_id = tk.IntVar(value=pygame.midi.get_default_output_id())
            midi_device_id = self.selected_midi_device_id.get() 
            if midi_device_id == -1:
                logger.warning("No default MIDI output device found.")
                messagebox.showwarning("MIDI Error", "No default MIDI output device was found. Audio generation will be disabled.")
                return
                
            self.midi_out = pygame.midi.Output(midi_device_id)
            device_info = pygame.midi.get_device_info(midi_device_id)
            logger.info(f"Successfully initialized shared MIDI output on device: {device_info[1].decode()}") 
            
        except Exception as e:
            logger.error(f"Global audio initialization error: {e}", exc_info=True)
            messagebox.showerror("Audio Error", f"A critical error occurred initializing the audio system:\n{e}")

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
        if self.grid_overlay_timer_id:
            self.after_cancel(self.grid_overlay_timer_id)
            self.grid_overlay_timer_id = None
     
        start_time = time.time()
        update_interval = 50  # ms
        
        self.grid_canvas.delete("all")

        w = self.grid_canvas.winfo_width()
        h = self.grid_canvas.winfo_height()
        active_track = self.get_active_track()
        
        if not active_track or w <= 1 or h <= 1:
            self.grid_overlay_timer_id = self.after(update_interval, self._update_grid_overlay)
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

        self.grid_overlay_timer_id = self.after(update_interval, self._update_grid_overlay)

    def _draw_active_notes(self, audio_generator: AudioGenerator, gw, gh, cell_w, cell_h):
        """Draw active notes for a specific audio generator."""
        if not audio_generator:
            return
            
        current_notes_snapshot = audio_generator.get_current_notes_snapshot()
        note_map_copy = {}
        
        with audio_generator.state_lock:
            note_map_copy = audio_generator.note_map.copy()
        
        active_track = self.get_active_track()
        
        for region_index in range(gw * gh):
            # Determine the note for this region
            if active_track and region_index in active_track.audio_generator.custom_note_mapping:
                note = active_track.audio_generator.custom_note_mapping[region_index]
                if note == -1:  # Disabled region
                    # Draw disabled region
                    row, col = divmod(region_index, gw)
                    x1, y1 = col * cell_w, row * cell_h
                    x2, y2 = x1 + cell_w, y1 + cell_h
                    self.grid_canvas.create_rectangle(x1 + 1, y1 + 1, x2 - 1, y2 - 1, 
                                                    fill='gray', outline='', width=0)
                    x_text, y_text = x1 + cell_w // 2, y1 + cell_h // 2
                    self.grid_canvas.create_text(x_text, y_text, text="OFF", fill='white', font=('Arial', 8))
                    continue
            elif region_index in note_map_copy:
                note = note_map_copy[region_index]
            else:
                continue
                
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
        
        if self.grid_overlay_timer_id:
            self.after_cancel(self.grid_overlay_timer_id)
        self.grid_overlay_timer_id = self.after(50, self._update_grid_overlay)

    def on_track_selected(self, event=None):
        """Handles switching between track tabs."""
        if not self.track_notebook or not self.tracks:
            return
            
        try:
            new_index = self.track_notebook.index(self.track_notebook.select())
            if new_index != self.active_track_index:
                self.active_track_index = new_index
                if self.grid_overlay_timer_id:
                    self.after_cancel(self.grid_overlay_timer_id)
                self.grid_overlay_timer_id = self.after(0, self._update_grid_overlay)
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

            # Calculate new root note value
            note_names = get_note_names()
            new_root_note = 60  # Default
            if new_root_note_name in note_names:
                new_root_note = 60 + note_names.index(new_root_note_name)

            # Only update if values actually changed
            settings_changed = (
                track.grid_width != new_width or
                track.grid_height != new_height or
                track.note_range != (new_min_note, new_max_note) or
                track.current_scale != new_scale or
                track.current_root_note != new_root_note
            )
            
            if not settings_changed:
                return
            
            track.grid_width = new_width
            track.grid_height = new_height
            track.note_range = (new_min_note, new_max_note)
            track.current_scale = new_scale
            track.current_root_note = new_root_note

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

        except Exception as e:
            logger.error(f"Camera playback error: {e}")
            self.status_msg.config(text=f"Playback error: {e}")

    def _populate_midi_devices(self):
        """Populates the MIDI output device menu."""
        self.midi_device_menu.delete(0, tk.END) # Clear existing entries
        
        if not pygame.midi.get_init():
            pygame.midi.init()

        for i in range(pygame.midi.get_count()):
            device_info = pygame.midi.get_device_info(i)
            if device_info[3] == 1:  # Check if it's an output device
                device_name = f"{i}: {device_info[1].decode()}"
                self.midi_device_menu.add_radiobutton(
                    label=device_name,
                    variable=self.selected_midi_device_id,
                    value=i,
                    command=self._on_midi_device_change
                )

    def _on_midi_device_change(self):
        """Handles MIDI output device change and re-initializes audio."""
        selected_id = self.selected_midi_device_id.get()
        logger.info(f"User selected new MIDI device ID: {selected_id}. Re-initializing audio.")

        # Stop all notes on all tracks before switching
        for track in self.tracks:
            if track.audio_generator:
                track.audio_generator.stop_all_notes()
        
        # Re-initialize the global audio system with the new device
        self._initialize_global_audio()
        
        # Re-link all existing tracks to the new midi_out object
        for track in self.tracks:
            track.midi_out = self.midi_out
            if track.audio_generator:
                track.audio_generator.midi_out = self.midi_out
                track.audio_generator.is_initialized = self.midi_out is not None

        messagebox.showinfo("MIDI Device Changed", f"MIDI output has been switched.")

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

    def _on_grid_click(self, event):
        """Handle clicks on the grid canvas."""
        active_track = self.get_active_track()
        if not active_track:
            return
            
        # Calculate which region was clicked
        w = self.grid_canvas.winfo_width()
        h = self.grid_canvas.winfo_height()
        
        if w <= 1 or h <= 1:
            return
            
        gw, gh = active_track.grid_width, active_track.grid_height
        cell_w, cell_h = w // gw, h // gh
        
        clicked_col = event.x // cell_w
        clicked_row = event.y // cell_h
        
        # Bounds check
        if clicked_col >= gw or clicked_row >= gh:
            return
            
        region_index = clicked_row * gw + clicked_col
        
        # Show note selection menu
        self._show_note_selection_menu(event.x_root, event.y_root, region_index)

    def _show_note_selection_menu(self, x, y, region_index):
        """Show a dropdown menu to select note for the clicked region."""
        active_track = self.get_active_track()
        if not active_track:
            return
            
        # Create popup menu
        popup = tk.Menu(self, tearoff=0)
        
        # Add "Disable" option
        popup.add_command(label="Disable (-1)", 
                        command=lambda: self._set_region_note(region_index, -1))
        popup.add_separator()
        
        # Add note options (0-127)
        # Group by octaves for better organization
        for octave in range(11):  # 0-10 covers MIDI range
            octave_menu = tk.Menu(popup, tearoff=0)
            start_note = octave * 12
            end_note = min(127, start_note + 11)
            
            for note in range(start_note, end_note + 1):
                note_name = self._get_note_name(note)
                octave_menu.add_command(label=f"{note_name} ({note})",
                                    command=lambda n=note: self._set_region_note(region_index, n))
            
            popup.add_cascade(label=f"Octave {octave} ({start_note}-{end_note})", menu=octave_menu)
        
        # Show current selection
        current_note = self._get_current_region_note(region_index)
        if current_note == -1:
            popup.add_separator()
            popup.add_command(label="Current: Disabled", state="disabled")
        else:
            note_name = self._get_note_name(current_note)
            popup.add_separator()
            popup.add_command(label=f"Current: {note_name} ({current_note})", state="disabled")
        
        try:
            popup.tk_popup(x, y)
        finally:
            popup.grab_release()

    def _set_region_note(self, region_index, note):
        """Set the note for a specific region."""
        active_track = self.get_active_track()
        if not active_track:
            return
            
        if note == -1:
            # Disable region
            active_track.audio_generator.custom_note_mapping[region_index] = -1
        else:
            # Set specific note
            active_track.audio_generator.custom_note_mapping[region_index] = note
        
        # Update audio generator if it exists
        if active_track.audio_generator:
            active_track.audio_generator.set_custom_note_mapping(region_index, note)
        
        # Refresh grid overlay
        self._update_grid_overlay()

    def _get_current_region_note(self, region_index):
        """Get the current note for a region."""
        active_track = self.get_active_track()
        if not active_track:
            return 0
            
        # Check custom mapping first
        if region_index in active_track.audio_generator.custom_note_mapping:
            return active_track.audio_generator.custom_note_mapping[region_index]
        
        # Fall back to default mapping
        if active_track.audio_generator and region_index in active_track.audio_generator.note_map:
            return active_track.audio_generator.note_map[region_index]
        
        return 0

    def _get_note_name(self, note_number):
        """Convert MIDI note number to note name."""
        if note_number < 0 or note_number > 127:
            return "Invalid"
        
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        octave = note_number // 12
        note = note_names[note_number % 12]
        return f"{note}{octave}"

    def __enter__(self):
        """Context manager entry."""
        return self

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
