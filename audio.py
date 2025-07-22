import cv2
import pygame
import pygame.midi
import threading
import numpy as np

from scipy.stats import entropy

from scales import generate_scale_notes, get_available_scales

from typing import Optional

from config import AudioConfig
from logger import StructuredLogger

logger = StructuredLogger.get_logger(__name__)

class AudioGenerator:
    """
    Generates MIDI instructions from video frames and synthesizes audio.
    """
    def __init__(self, midi_out: pygame.midi.Output, config: Optional[AudioConfig] = None):
        """Initialize the audio generator."""
        self.config = config or AudioConfig()
        self.grid_width = self.config.DEFAULT_GRID_WIDTH
        self.grid_height = self.config.DEFAULT_GRID_HEIGHT
        self.note_range = self.config.DEFAULT_NOTE_RANGE
        self.scale_name = self.config.SCALE
        self.root_note = self.config.ROOT_NOTE
        self.sensitivity = self.config.SENSITIVITY
        self.metric = self.config.DEFAULT_METRIC

        self.total_regions = self.grid_width * self.grid_height
        self.note_map = self._create_note_map()
        
        self.is_initialized = False
        self.midi_out = midi_out # Use the passed-in shared MIDI output
        self.current_notes: dict[int, int] = {}
        self.state_lock = threading.RLock()
        self._current_notes_snapshot: dict[int, int] = {}
        
        if self.midi_out is not None:
            self.is_initialized = True
            logger.info("AudioGenerator successfully linked to shared MIDI output.")
        else:
            logger.error("AudioGenerator received an invalid MIDI output object.")
    
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
    
    def analyze_frame(self, frame):
        """
        Analyzes a video frame and extracts metric values for each grid region.
        Supports metrics: brightness, red_channel, green_channel, blue_channel,
        hue, saturation, contrast, color_temperature, color_entropy.
        """
        # Early exit for empty frame
        if frame is None:
            return {}

        # Ensure valid frame dimensions
        ndim = frame.ndim
        h, w = frame.shape[:2]
        rh, rw = h // self.grid_height, w // self.grid_width

        # Prepare processed_frame for simple pixel-based metrics
        simple_metrics = {
            'brightness': lambda f: cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) if ndim == 3 else f,
            'red_channel': lambda f: f[:, :, 0] if ndim == 3 else None,
            'green_channel': lambda f: f[:, :, 1] if ndim == 3 else None,
            'blue_channel': lambda f: f[:, :, 2] if ndim == 3 else None,
            'hue': lambda f: cv2.cvtColor(f, cv2.COLOR_RGB2HSV)[:, :, 0] if ndim == 3 else None,
            'saturation': lambda f: cv2.cvtColor(f, cv2.COLOR_RGB2HSV)[:, :, 1] if ndim == 3 else None,
        }

        metric = self.metric
        # Handle complex per-block metrics separately
        if metric == 'contrast':
            gray = simple_metrics['brightness'](frame)
            return self._compute_std(gray, rh, rw)
        if metric == 'color_temperature':
            if ndim != 3:
                return {}
            return self._compute_color_temp(frame, rh, rw)
        if metric == 'color_entropy':
            gray = simple_metrics['brightness'](frame)
            return self._compute_entropy(gray, rh, rw)

        # Simple resize-based metrics
        if metric in simple_metrics:
            processed = simple_metrics[metric](frame)
            if processed is None:
                return {}
            resized = cv2.resize(processed, (self.grid_width, self.grid_height), interpolation=cv2.INTER_AREA)
            flat = resized.flatten().astype(np.float32)
            if metric == 'hue':
                flat /= 179.0
            else:
                flat /= 255.0
            return {i: flat[i] for i in range(self.grid_width * self.grid_height)}

        # Fallback to brightness
        logger.error(f"Frame analysis error, couldn't use metric: {metric}")
        processed = simple_metrics['brightness'](frame)
        resized = cv2.resize(processed, (self.grid_width, self.grid_height), interpolation=cv2.INTER_AREA)
        flat = resized.flatten().astype(np.float32) / 255.0
        return {i: flat[i] for i in range(self.grid_width * self.grid_height)}

    def _compute_std(self, gray, rh, rw):
        values = {}
        idx = 0
        for gy in range(self.grid_height):
            for gx in range(self.grid_width):
                block = gray[gy*rh:(gy+1)*rh, gx*rw:(gx+1)*rw]
                std = block.std() / 127.5
                values[idx] = min(std, 1.0)
                idx += 1
        return values

    def _compute_color_temp(self, frame, rh, rw):
        values = {}
        idx = 0
        for gy in range(self.grid_height):
            for gx in range(self.grid_width):
                block = frame[gy*rh:(gy+1)*rh, gx*rw:(gx+1)*rw]
                r = block[:, :, 0].mean()
                b = block[:, :, 2].mean()
                temp = (r - b) / (r + b + 1e-6)
                values[idx] = (temp + 1.0) / 2.0
                idx += 1
        return values

    def _compute_entropy(self, gray, rh, rw):
        from scipy.stats import entropy

        values = {}
        idx = 0
        for gy in range(self.grid_height):
            for gx in range(self.grid_width):
                block = gray[gy*rh:(gy+1)*rh, gx*rw:(gx+1)*rw]
                hist = cv2.calcHist([block], [0], None, [256], [0,256]).flatten()
                probs = hist / hist.sum() if hist.sum() > 0 else np.zeros_like(hist)
                ent = entropy(probs, base=2) / 8.0
                values[idx] = min(ent, 1.0)
                idx += 1
        return values

    def metric_to_velocity(self, brightness):
        """Convert brightness value (0-1) to MIDI velocity (0-127)."""
        velocity = int(brightness * 127 * (self.sensitivity))
        return max(0, min(127, velocity))
    
    def generate_midi_events(self, metric_values: dict[int, float]) -> list[tuple[str, int, int]]:
        """Generate MIDI events from metric values."""
        midi_events = []
        
        with self.state_lock:
            for region_index, metric_value in metric_values.items():
                if region_index not in self.note_map:
                    continue
                    
                note = self.note_map[region_index]
                velocity = self.metric_to_velocity(metric_value)
                
                is_playing = note in self.current_notes
                should_play = metric_value > self.config.NOTE_ON_THRESHOLD
                should_stop = metric_value <= self.config.NOTE_OFF_THRESHOLD

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
        with self.state_lock:
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
            
        # Analyze frame using selected metric
        metric_values = self.analyze_frame(frame)
        
        # Generate MIDI events
        midi_events = self.generate_midi_events(metric_values)
        
        # Play MIDI events
        self.play_midi_events(midi_events)
    
    def stop_all_notes(self):
        """Stop all currently playing notes."""
        with self.state_lock:
            for note in list(self.current_notes.keys()):
                try:
                    if self.midi_out:
                        self.midi_out.note_off(note, self.current_notes[note])
                except Exception as e:
                    logger.error(f"Error stopping note {note}: {e}")
            self.current_notes.clear()

    def set_metric(self, metric: str):
        """Set the metric used for MIDI generation."""
        with self.state_lock:
            if metric in self.config.AVAILABLE_METRICS:
                self.metric = metric
            else:
                logger.warning(f"Invalid metric: {metric}")
        self.stop_all_notes()  # Stop current notes as metric changed
    
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
    
    def set_sensitivity(self, sensitivity: float):
        """Set sensitivity multiplier for MIDI generation."""
        with self.state_lock:
            self.sensitivity = max(0.0, min(10.0, sensitivity))
    
    def cleanup(self) -> None:
        """Clean up audio resources."""
        logger.info("Cleaning up audio system...")
        try:
            with self.state_lock:
                for note in list(self.current_notes.keys()):
                    try:
                        if self.midi_out:
                            self.midi_out.note_off(note, self.current_notes[note])
                    except Exception as e:
                        logger.error(f"Error stopping note {note}: {e}")
                self.current_notes.clear()
                self._current_notes_snapshot.clear()
            
            if self.midi_out:
                try:
                    for channel in range(16):
                        self.midi_out.write_short(0xB0 | channel, 123, 0)
                    self.midi_out.close()
                except Exception as e:
                    logger.error(f"Error closing MIDI output: {e}", exc_info=True)
                finally:
                    self.midi_out = None
            
            # --- REMOVE THE FOLLOWING LINES ---
            # if pygame.midi.get_init():
            #     pygame.midi.quit()
            # if pygame.mixer.get_init():
            #     pygame.mixer.quit()
                    
            self.is_initialized = False
            logger.info("Audio system cleaned up successfully.")
            
        except Exception as e:
            logger.error(f"An error occurred during audio cleanup: {e}", exc_info=True)
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()