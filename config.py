from typing import NamedTuple
from dataclasses import dataclass

class VideoConfig(NamedTuple):
    """Video processing configuration constants."""
    DISPLAY_QUEUE_SIZE: int = 20
    PROCESSING_QUEUE_SIZE: int = 200
    DEFAULT_FPS: float = 30.0
    UI_UPDATE_QUEUE_SIZE: int = 50
    STATS_UPDATE_INTERVAL_MS: int = 500
    UI_UPDATE_INTERVAL_MS: int = 33
    THREAD_JOIN_TIMEOUT: float = 2.0

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
    MIDI_VELOCITY_RANGE: tuple[int, int] = (0, 127)
    MIDI_NOTE_RANGE: tuple[int, int] = (0, 127)

class UIConfig(NamedTuple):
    """UI configuration constants."""
    WINDOW_GEOMETRY: str = '900x700'
    GRID_OVERLAY_FPS: int = 20
    DEFAULT_GRID_WIDTH: int = 20
    DEFAULT_GRID_HEIGHT: int = 1
    DEFAULT_NOTE_RANGE: tuple = (40, 85)
    MIN_PANEL_SIZE: tuple = (1, 1)

@dataclass
class LogConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    enable_console: bool = True
    enable_file: bool = False
    file_path: str = "video_midi.log"
