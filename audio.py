# audio.py
import numpy as np
import cv2
import pygame
import pygame.midi
import threading
import os
from scales import generate_scale_notes, get_available_scales

import logging
from typing import Optional

from config import AudioConfig
from logger import StructuredLogger

logger = StructuredLogger.get_logger(__name__)

class AudioGenerator:
    """
    Generates MIDI instructions from video frames and synthesizes audio using soundfonts.
    """
    def __init__(self,
                config: Optional[AudioConfig] = None,
                grid_width: int = 4,
                grid_height: int = 3,
                note_range: tuple[int, int] = (0, 127),
                soundfont_path: Optional[str] = None,
                scale_name: str = "Pentatonic Major",
                root_note: int = 60):
        """Initialize the audio generator."""
        self.config = config or AudioConfig()
        self.grid_width = grid_width
        self.grid_height = grid_height
        self.note_range = note_range
        self.soundfont_path = soundfont_path
        self.scale_name = scale_name
        self.root_note = root_note

        # Calculate total regions and note mapping
        self.total_regions = grid_width * grid_height
        self.note_map = self._create_note_map()
        
        # Audio state
        self.is_initialized = False
        self.midi_out = None
        self.current_notes: dict[int, int] = {}  # {note: velocity}
        self.note_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self._current_notes_snapshot: dict[int, int] = {}
        
        # Initialize pygame mixer for soundfont playback
        self._initialize_audio()
    
    def _create_note_map(self):
        """Create mapping from grid regions to scale notes."""
        note_map = {}
        
        # Generate scale notes within the note range
        scale_notes = generate_scale_notes(self.root_note, self.scale_name, self.note_range)
        
        if not scale_notes:
            # Fallback to chromatic if no scale notes found
            min_note, max_note = self.note_range
            scale_notes = list(range(min_note, max_note + 1))
        
        # Map grid regions to scale notes (cycle through scale if needed)
        for i in range(self.total_regions):
            note_index = i % len(scale_notes)
            note_map[i] = scale_notes[note_index]
        
        return note_map
    
    def set_scale(self, scale_name, root_note):
        """Change scale and root note, recalculate note mapping."""
        with self.state_lock:
            self.scale_name = scale_name
            self.root_note = root_note
            self.note_map = self._create_note_map()
        self.stop_all_notes()  # Stop current notes as mapping changed

    def get_available_scales(self):
        """Return list of available scales."""
        return get_available_scales()
    
    def _initialize_audio(self) -> bool:
        """Initialize pygame mixer and MIDI output."""
        try:
            pygame.mixer.pre_init(
                frequency=self.config.DEFAULT_FREQUENCY,
                size=-16,
                channels=2,
                buffer=self.config.BUFFER_SIZE
            )
            pygame.mixer.init()
            pygame.midi.init()
            
            midi_device_id = pygame.midi.get_default_output_id()
            if midi_device_id == -1:
                logger.warning("No MIDI output device found.")
                return False
                
            self.midi_out = pygame.midi.Output(midi_device_id)
            
            if self.soundfont_path and os.path.exists(self.soundfont_path):
                logger.info(f"Soundfont path set: {self.soundfont_path}")
                logger.info("Note: Full soundfont support requires fluidsynth integration.")
            
            self.is_initialized = True
            logger.info("Audio system initialized successfully.")
            return True
            
        except Exception as e:
            logger.error(f"Audio initialization error: {e}", exc_info=True)
            return False
    
    def analyze_frame(self, frame):
        """
        Analyzes a video frame and extracts brightness values for each grid region.
        This optimized version expects a GRAYSCALE frame.

        Args:
            frame: OpenCV frame (single-channel grayscale format)

        Returns:
            dict: {region_index: brightness_value}
        """
        if frame is None:
            return {}

        # Resize the entire grayscale frame to the grid dimensions in one go.
        # cv2.INTER_AREA is efficient for downscaling.
        resized = cv2.resize(frame, (self.grid_width, self.grid_height), interpolation=cv2.INTER_AREA)

        brightness_values = {}
        total_regions = self.grid_width * self.grid_height

        # Read the brightness values directly from the resized image using numpy operations
        brightness_array = resized.flatten() / 255.0
        for i in range(min(total_regions, len(brightness_array))):
            brightness_values[i] = brightness_array[i]

        return brightness_values
    
    def brightness_to_velocity(self, brightness):
        """Convert brightness value (0-1) to MIDI velocity (0-127)."""
        return int(brightness * 127)
    
    def generate_midi_events(self, brightness_values: dict[int, float]) -> list[tuple[str, int, int]]:
        """Generate MIDI events from brightness values."""
        midi_events = []
        
        with self.note_lock:
            for region_index, brightness in brightness_values.items():
                if region_index not in self.note_map:
                    continue
                    
                note = self.note_map[region_index]
                velocity = self.brightness_to_velocity(brightness)
                
                is_playing = note in self.current_notes
                should_play = brightness > self.config.NOTE_ON_THRESHOLD
                should_stop = brightness <= self.config.NOTE_OFF_THRESHOLD

                if should_play and not is_playing:
                    midi_events.append(('note_on', note, velocity))
                    self.current_notes[note] = velocity
                elif should_play and is_playing:
                    current_velocity = self.current_notes[note]
                    if abs(velocity - current_velocity) > self.config.VELOCITY_CHANGE_THRESHOLD:
                        midi_events.append(('note_off', note, current_velocity))
                        midi_events.append(('note_on', note, velocity))
                        self.current_notes[note] = velocity
                elif should_stop and is_playing:
                    midi_events.append(('note_off', note, self.current_notes.get(note, 0)))
                    del self.current_notes[note]
            
            self._current_notes_snapshot = self.current_notes.copy()
        
        return midi_events

    def get_current_notes_snapshot(self):
        """Get a thread-safe snapshot of current notes for UI display."""
        with self.note_lock:
            return self._current_notes_snapshot.copy()
    
    def play_midi_events(self, midi_events):
        """Play MIDI events through the output device."""
        if not self.is_initialized or not self.midi_out:
            return
            
        for action, note, velocity in midi_events:
            try:
                if action == 'note_on':
                    self.midi_out.note_on(note, velocity)
                elif action == 'note_off':
                    self.midi_out.note_off(note, velocity)
            except Exception as e:
                logger.error(f"MIDI playback error: {e}")
    
    def process_frame(self, frame):
        """
        Process a single frame to generate and play audio.
        
        Args:
            frame: OpenCV frame
        """
        if not self.is_initialized:
            return
            
        # Analyze frame
        brightness_values = self.analyze_frame(frame)
        
        # Generate MIDI events
        midi_events = self.generate_midi_events(brightness_values)
        
        # Play MIDI events
        self.play_midi_events(midi_events)
    
    def stop_all_notes(self):
        """Stop all currently playing notes."""
        with self.note_lock:
            for note in list(self.current_notes.keys()):
                try:
                    if self.midi_out:
                        self.midi_out.note_off(note, self.current_notes[note])
                except Exception as e:
                    logger.error(f"Error stopping note {note}: {e}")
            self.current_notes.clear()
    
    def set_soundfont(self, soundfont_path):
        """Set a new soundfont file."""
        self.soundfont_path = soundfont_path
        if os.path.exists(soundfont_path):
            logger.info(f"Soundfont set to: {soundfont_path}")
        else:
            logger.error(f"Soundfont file not found: {soundfont_path}")
    
    def set_grid_size(self, width, height):
        """Change grid size and recalculate note mapping."""
        with self.state_lock:
            self.grid_width = width
            self.grid_height = height
            self.total_regions = width * height
            self.note_map = self._create_note_map()
        self.stop_all_notes()  # Stop current notes as mapping changed

    def set_note_range(self, min_note, max_note):
        """Change note range and recalculate note mapping."""
        with self.state_lock:
            self.note_range = (min_note, max_note)
            self.note_map = self._create_note_map()
        self.stop_all_notes()  # Stop current notes as mapping changed
    
    def get_grid_visualization(self, frame):
        """
        Create a visualization of the grid overlay on the frame.
        
        Args:
            frame: OpenCV frame
            
        Returns:
            frame with grid overlay
        """
        if frame is None:
            return None
            
        height, width = frame.shape[:2]
        region_width = width // self.grid_width
        region_height = height // self.grid_height
        
        # Create a copy for visualization
        vis_frame = frame.copy()
        
        # Draw grid lines
        for i in range(1, self.grid_width):
            x = i * region_width
            cv2.line(vis_frame, (x, 0), (x, height), (0, 255, 0), 2)
            
        for i in range(1, self.grid_height):
            y = i * region_height
            cv2.line(vis_frame, (0, y), (width, y), (0, 255, 0), 2)
        
        # Draw region labels with notes
        for row in range(self.grid_height):
            for col in range(self.grid_width):
                region_index = row * self.grid_width + col
                note = self.note_map.get(region_index, 0)
                
                # Position for text
                x = col * region_width + 10
                y = row * region_height + 30
                
                # Draw note number
                cv2.putText(vis_frame, f"N{note}", (x, y), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                # Show if note is currently playing
                if note in self.current_notes:
                    cv2.putText(vis_frame, "ON", (x, y + 25), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        return vis_frame
    
    def cleanup(self) -> None:
        """Clean up audio resources."""
        logger.info("Cleaning up audio system...")
        try:
            self.stop_all_notes()
            
            if self.midi_out:
                try:
                    for channel in range(16):
                        self.midi_out.write_short(0xB0 | channel, 123, 0)
                    self.midi_out.close()
                except Exception as e:
                    logger.error(f"Error closing MIDI output: {e}", exc_info=True)
                finally:
                    self.midi_out = None
            
            if pygame.midi.get_init():
                pygame.midi.quit()
            if pygame.mixer.get_init():
                pygame.mixer.quit()

            with self.note_lock:
                self.current_notes.clear()
                self._current_notes_snapshot.clear()
                
            self.is_initialized = False
            logger.info("Audio system cleaned up successfully.")
            
        except Exception as e:
            logger.error(f"An error occurred during audio cleanup: {e}", exc_info=True)
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()