# audio.py
import numpy as np
import cv2
import pygame
import pygame.midi
import threading
import time
from collections import defaultdict
import os

class AudioGenerator:
    """
    Generates MIDI instructions from video frames and synthesizes audio using soundfonts.
    """
    def __init__(self, grid_width=4, grid_height=3, note_range=(50, 62), soundfont_path=None):
        """
        Initialize the audio generator.
        
        Args:
            grid_width (int): Number of horizontal grid divisions
            grid_height (int): Number of vertical grid divisions
            note_range (tuple): (min_note, max_note) MIDI note range
            soundfont_path (str): Path to soundfont file (.sf2)
        """
        self.grid_width = grid_width
        self.grid_height = grid_height
        self.note_range = note_range
        self.soundfont_path = soundfont_path
        
        # Calculate total regions and note mapping
        self.total_regions = grid_width * grid_height
        self.note_map = self._create_note_map()
        
        # Audio state
        self.is_initialized = False
        self.midi_out = None
        self.current_notes = {}  # Track currently playing notes
        self.note_lock = threading.Lock()
        
        # Processing state
        self.is_processing = False
        self.processing_thread = None
        
        # Initialize pygame mixer for soundfont playback
        self._initialize_audio()
    
    def _create_note_map(self):
        """Create mapping from grid regions to MIDI notes."""
        note_map = {}
        min_note, max_note = self.note_range
        note_span = max_note - min_note
        
        for i in range(self.total_regions):
            if self.total_regions == 1:
                note = min_note
            else:
                note = min_note + int((i / (self.total_regions - 1)) * note_span)
            note_map[i] = note
            
        return note_map
    
    def _initialize_audio(self):
        """Initialize pygame mixer and MIDI output."""
        try:
            # Initialize pygame mixer
            pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.mixer.init()
            
            # Initialize MIDI
            pygame.midi.init()
            
            # Find default MIDI output device
            midi_device_id = pygame.midi.get_default_output_id()
            if midi_device_id == -1:
                print("No MIDI output device found")
                return False
                
            self.midi_out = pygame.midi.Output(midi_device_id)
            
            # Load soundfont if available
            if self.soundfont_path and os.path.exists(self.soundfont_path):
                try:
                    # Note: pygame doesn't directly support soundfonts
                    # For full soundfont support, you'd need fluidsynth or similar
                    print(f"Soundfont path set: {self.soundfont_path}")
                    print("Note: Full soundfont support requires fluidsynth integration")
                except Exception as e:
                    print(f"Soundfont loading error: {e}")
            
            self.is_initialized = True
            print("Audio system initialized successfully")
            return True
            
        except Exception as e:
            print(f"Audio initialization error: {e}")
            return False
    
    def analyze_frame(self, frame):
        """
        Analyze a video frame and extract brightness values for each grid region.
        
        Args:
            frame: OpenCV frame (BGR format)
            
        Returns:
            dict: {region_index: brightness_value}
        """
        if frame is None:
            return {}
        
        # Convert to grayscale for brightness analysis
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape
        
        # Calculate region dimensions
        region_width = width // self.grid_width
        region_height = height // self.grid_height
        
        brightness_values = {}
        
        for row in range(self.grid_height):
            for col in range(self.grid_width):
                # Calculate region boundaries
                y1 = row * region_height
                y2 = (row + 1) * region_height if row < self.grid_height - 1 else height
                x1 = col * region_width
                x2 = (col + 1) * region_width if col < self.grid_width - 1 else width
                
                # Extract region
                region = gray[y1:y2, x1:x2]
                
                # Calculate average brightness (0-255) and normalize to (0-1)
                brightness = np.mean(region) / 255.0
                
                # Convert to region index
                region_index = row * self.grid_width + col
                brightness_values[region_index] = brightness
        
        return brightness_values
    
    def brightness_to_velocity(self, brightness):
        """Convert brightness value (0-1) to MIDI velocity (0-127)."""
        return int(brightness * 127)
    
    def generate_midi_events(self, brightness_values, velocity_threshold=0.1):
        """
        Generate MIDI events from brightness values.
        
        Args:
            brightness_values (dict): {region_index: brightness_value}
            velocity_threshold (float): Minimum brightness to trigger note
            
        Returns:
            list: MIDI events [(action, note, velocity), ...]
        """
        midi_events = []
        
        with self.note_lock:
            for region_index, brightness in brightness_values.items():
                if region_index not in self.note_map:
                    continue
                    
                note = self.note_map[region_index]
                velocity = self.brightness_to_velocity(brightness)
                
                # Check if note should be playing
                should_play = brightness > velocity_threshold
                is_playing = note in self.current_notes
                
                if should_play and not is_playing:
                    # Start note
                    midi_events.append(('note_on', note, velocity))
                    self.current_notes[note] = velocity
                    
                elif should_play and is_playing:
                    # Update velocity if significantly different
                    current_velocity = self.current_notes[note]
                    if abs(velocity - current_velocity) > 10:  # Threshold for velocity change
                        midi_events.append(('note_off', note, current_velocity))
                        midi_events.append(('note_on', note, velocity))
                        self.current_notes[note] = velocity
                        
                elif not should_play and is_playing:
                    # Stop note
                    midi_events.append(('note_off', note, self.current_notes[note]))
                    del self.current_notes[note]
        
        return midi_events
    
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
                print(f"MIDI playback error: {e}")
    
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
                    print(f"Error stopping note {note}: {e}")
            self.current_notes.clear()
    
    def set_soundfont(self, soundfont_path):
        """Set a new soundfont file."""
        self.soundfont_path = soundfont_path
        if os.path.exists(soundfont_path):
            print(f"Soundfont set to: {soundfont_path}")
        else:
            print(f"Soundfont file not found: {soundfont_path}")
    
    def set_grid_size(self, width, height):
        """Change grid size and recalculate note mapping."""
        self.grid_width = width
        self.grid_height = height
        self.total_regions = width * height
        self.note_map = self._create_note_map()
        self.stop_all_notes()  # Stop current notes as mapping changed
    
    def set_note_range(self, min_note, max_note):
        """Change note range and recalculate note mapping."""
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
    
    def cleanup(self):
        """Clean up audio resources."""
        try:
            self.stop_all_notes()
            
            if self.midi_out:
                self.midi_out.close()
                self.midi_out = None
            
            if pygame.mixer.get_init():
                pygame.mixer.quit()
                
            if pygame.midi.get_init():
                pygame.midi.quit()
                
            self.is_initialized = False
            print("Audio system cleaned up")
            
        except Exception as e:
            print(f"Audio cleanup error: {e}")
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()