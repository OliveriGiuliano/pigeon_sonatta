from tkinter import filedialog, messagebox
import os

from video import VideoManager  

from logger import StructuredLogger

logger = StructuredLogger.get_logger(__name__)

class VideoController:
    def __init__(self, parent_window, track_manager, status_callback, stats_callback, frame_processor):
        self.parent_window = parent_window
        self.track_manager = track_manager
        self.video_panel = None
        self.status_callback = status_callback  # Function to update status
        self.stats_callback = stats_callback    # Function to update stats
        self.frame_processor = frame_processor  # Function to process frames
        self.video_manager = None
        self.current_video_path = None
        self.current_camera_index = None
        self.update_timer = None

    def _init_video_manager(self, event=None):
        """Initialize Video manager only once and when frame is ready."""
        if not self.video_manager:
            try:
                # Ensure the frame is fully mapped before initializing video
                self.video_panel.update_idletasks()
                self.video_manager = VideoManager(self.video_panel, frame_callback=self._process_frame)
                logger.info("Video manager initialized successfully")
                
                # Rebind window handle on resize
                self.video_panel.bind("<Configure>", self._on_frame_configure)
                
            except Exception as e:
                logger.error(f"Video initialization failed: {e}")
                self.parent_window.status_msg.config(text=f"Video Error: {e}")

    def _process_frame(self, frame):
        """Process video frame for audio generation across all enabled tracks."""
        if frame is None:
            return
            
        try:
            for track in self.track_manager.tracks:
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
            self.parent_window.after(500, lambda: self._start_video_playback(path))
            
        except Exception as e:
            logger.error(f"Video loading error: {e}")
            self.parent_window.status_msg.config(text=f"Error loading video: {e}")
            messagebox.showerror("Video Error", f"Failed to load video:\n{e}")

    def _start_video_playback(self, path):
        """Start video playback after media is loaded."""
        try:
            self.video_manager.play()
            self.parent_window.status_msg.config(text=f"Playing: {os.path.basename(path)}")
                
            self.parent_window.after(100, self._update_stats)
            self.parent_window.after(50, self._process_ui_updates)
        except Exception as e:
            logger.error(f"Playback error: {e}")
            self.parent_window.status_msg.config(text=f"Playback error: {e}")

    def _process_ui_updates(self):
        """Process UI updates from video manager in main thread."""
        if self.video_manager:
            self.video_manager.process_ui_updates()
        
        # Schedule next update
        if self.video_manager and self.video_manager.is_playing():
            self.parent_window.after(33, self._process_ui_updates)  # ~30 FPS UI updates
        else:
            self.parent_window.after(100, self._process_ui_updates)  # Slower polling when not playing

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
            self.parent_window.after(100, self._update_stats)

    def pause_video(self):
        if self.video_manager:
            self.video_manager.pause()
            for track in self.track_manager.tracks:
                if track.audio_generator:
                    track.audio_generator.stop_all_notes()

    def stop_video(self):
        if self.video_manager:
            self.video_manager.stop()
            for track in self.track_manager.tracks:
                if track.audio_generator:
                    track.audio_generator.stop_all_notes()
            self.parent_window.stats_lbl.config(text="FPS: -- | Target FPS: -- | Latency: -- | Target Latency: --")

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

            self.parent_window.stats_lbl.config(text=stats_text)
            
            # Schedule the next update
            self.parent_window.after(500, self._update_stats)
        else:
            # If not playing, check again in a bit without resetting the label immediately,
            # allowing stats to persist during pause.
            self.parent_window.after(500, self._update_stats)

    def open_camera(self):
        """Opens a camera device for live video input."""
        camera_index = 0  # Default to first camera
        self.current_camera_index = camera_index
        self.current_video_path = None  # Clear video path
        
        try:
            self._load_camera(camera_index)
        except Exception as e:
            logger.error(f"Camera error: {e}")
            self.parent_window.status_msg.config(text=f"Camera Error: {e}")
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
        self.parent_window.after(500, lambda: self._start_camera_playback(camera_index))

    def _start_camera_playback(self, camera_index):
        try:
            self.video_manager.play()
            self.parent_window.status_msg.config(text=f"Camera {camera_index}")
            self.parent_window.after(100, self._update_stats)
            self.parent_window.after(50, self._process_ui_updates)
        except Exception as e:
            logger.error(f"Camera playback error: {e}")
            self.parent_window.status_msg.config(text=f"Playback error: {e}")

    def _on_frame_configure(self, event):
        # Could be used if resizing video window changes viewport
        pass

    def is_playing(self):
        """Check if video is currently playing."""
        return self.video_manager and self.video_manager.is_playing()

    def cleanup(self):
        """Clean up video resources."""
        if self.video_manager:
            self.video_manager.cleanup()
            self.video_manager = None