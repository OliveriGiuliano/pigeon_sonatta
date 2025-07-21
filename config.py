from typing import NamedTuple
from dataclasses import dataclass

class VideoConfig(NamedTuple):
    """Video processing configuration constants."""
    DISPLAY_QUEUE_SIZE: int = 20
    PROCESSING_QUEUE_SIZE: int = 200
    UI_UPDATE_QUEUE_SIZE: int = 50

@dataclass
class AudioConfig:
    """Audio processing configuration constants."""
    DEFAULT_FREQUENCY: int = 44100
    BUFFER_SIZE: int = 512
    # MIDI processing thresholds
    NOTE_ON_THRESHOLD: float = 0.1  # Brightness threshold to trigger a note (0-1)
    NOTE_OFF_THRESHOLD: float = 0.05 # Brightness threshold to release a note (0-1)
    VELOCITY_CHANGE_THRESHOLD: int = 10 # Min change in velocity (0-127) to re-trigger a note
    # MIDI value ranges
    MIDI_NOTE_RANGE: tuple[int, int] = (0, 127) # Midi standard
    DEFAULT_NOTE_RANGE: tuple = (40, 127) # Our range
    SCALE: str = "Pentatonic Major"
    SENSITIVITY: float = 1.0
    ROOT_NOTE: int = 60
    DEFAULT_GRID_WIDTH: int = 20
    DEFAULT_GRID_HEIGHT: int = 1
    DEFAULT_METRIC = "brightness"
    AVAILABLE_METRICS = [
        "brightness", 
        "red_channel", 
        "green_channel", 
        "blue_channel", 
        "hue", 
        "saturation",
        "contrast",
        "color_temperature",
        "color_entropy"
    ]

class UIConfig(NamedTuple):
    """UI configuration constants."""
    WINDOW_GEOMETRY: str = '900x700'


@dataclass
class LogConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    enable_console: bool = True
    enable_file: bool = False
    file_path: str = "log.log"
