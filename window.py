import tkinter as tk
from tkinter import messagebox
import atexit

from config import UIConfig, AudioConfig, VideoConfig
from logger import StructuredLogger

from video_controller import VideoController
from ui_builder import UIBuilder
from track_manager import TrackManager
from menu_manager import MenuManager
from grid_visualizer import GridVisualizer
from audio_system_manager import AudioSystemManager

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

        # Initialize managers to give to the UI builder
        self.audio_system_manager = AudioSystemManager(self.audio_config)
        self.track_manager = TrackManager(
            self,
            self.audio_system_manager.midi_out
        )
        self.video_controller = VideoController(
            self,
            self.track_manager,
            self._update_status,
            self._update_stats_display,
            self._process_frame
        )

        # Create UI builder with proper parent reference
        self.ui_builder = UIBuilder(self, self.video_controller, self.track_manager, self.audio_config)
        
        # Build UI and get required widgets
        video_panel, grid_canvas, track_notebook, status_msg, stats_lbl = self.ui_builder.build_main_interface()
        
        self.video_panel = video_panel
        self.grid_canvas = grid_canvas
        self.track_notebook = track_notebook
        self.status_msg = status_msg
        self.stats_lbl = stats_lbl

        # Set widget links now that the UI is built 
        self.video_controller.video_panel = self.video_panel
        self.track_manager.ui_builder = self.ui_builder
        self.audio_system_manager.track_manager = self.track_manager

        # Initialize other managers
        self.track_manager.track_notebook = self.track_notebook
        self.track_manager.add_track() # create initial track

        # Initialize other managers
        self.grid_visualizer = GridVisualizer(self, self.grid_canvas, self.track_manager)
        self.track_manager.grid_visualizer = self.grid_visualizer
        
        self.menu_manager = MenuManager(self, self.video_controller, self.audio_system_manager)

        # Update UI builder references now that other components exist
        self.ui_builder.video_controller = self.video_controller
        self.ui_builder.track_manager = self.track_manager

        # Setup callbacks
        self.audio_system_manager.add_device_change_callback(self._on_audio_device_changed)
        self.track_notebook.bind("<<NotebookTabChanged>>", self.track_manager.on_track_selected)
        
        # Initialize video after frame is created and mapped
        self.video_panel.bind("<Map>", self.video_controller._init_video_manager)

        # Register cleanup
        atexit.register(self.cleanup)

    def _update_status(self, message):
        """Update status bar message."""
        self.status_msg.config(text=message)

    def _update_stats_display(self, stats_text):
        """Update statistics display."""
        self.stats_lbl.config(text=stats_text)

    def _process_frame(self, frame):
        """Process video frame for all enabled tracks."""
        if frame is None:
            return
        try:
            for track in self.track_manager.tracks:
                if track.audio_enabled and track.audio_generator:
                    track.audio_generator.process_frame(frame)
        except Exception as e:
            logger.error(f"Frame processing error: {e}")

    def _on_audio_device_changed(self):
        """Handle MIDI device change."""
        self.track_manager.update_midi_output(self.audio_system_manager.midi_out)
        self.menu_manager.update_midi_device_menu()
        messagebox.showinfo("MIDI Device Changed", "MIDI output has been switched.")

    def cleanup(self):
        """Clean up all resources."""
        # Prevent double cleanup
        logger.info("Cleaning up all components...")
        
        cleanup_errors = []
        
        # Stop visualization first
        if hasattr(self, 'grid_visualizer'):
            self.grid_visualizer.stop_visualization()
        
        # Clean up tracks
        if hasattr(self, 'track_manager'):
            try:
                self.track_manager.cleanup()
            except Exception as e:
                cleanup_errors.append(f"Track manager cleanup error: {e}")
        
        # Clean up video
        if hasattr(self, 'video_controller'):
            try:
                self.video_controller.cleanup()
            except Exception as e:
                cleanup_errors.append(f"Video controller cleanup error: {e}")
        
        # Clean up audio system last
        if hasattr(self, 'audio_system_manager'):
            try:
                self.audio_system_manager.cleanup()
            except Exception as e:
                cleanup_errors.append(f"Audio system cleanup error: {e}")

        if cleanup_errors:
            logger.error(f"Cleanup completed with errors: {'; '.join(cleanup_errors)}")
        else:
            logger.info("Cleanup completed successfully")

    def on_closing(self):
        """Handle window closing."""
        logger.info("Closing application...")
        self.cleanup()
        self.destroy()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False