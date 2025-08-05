import av
import tkinter as tk
from PIL import Image, ImageTk
import threading
import queue
import time
import numpy as np
import cv2
import platform

from typing import Optional, Callable
from config import VideoConfig
from logger import StructuredLogger

logger = StructuredLogger.get_logger(__name__)

class VideoManager:
    """
    Manages video playback using PyAV (FFmpeg bindings) in a unified pipeline.
    It handles decoding, display, and frame processing in separate threads for
    better performance and synchronization.
    """
    def __init__(self,
                video_panel: tk.Widget,
                frame_callback: Optional[Callable[[np.ndarray], None]] = None,
                config: Optional[VideoConfig] = None):
        """Initializes the VideoManager."""
        self.video_panel = video_panel
        self.frame_callback = frame_callback
        self.config = config or VideoConfig()

        # PyAV and video state
        self.container: Optional[av.container.Container] = None
        self.video_stream: Optional[av.video.stream.VideoStream] = None
        self.fps: float = 0.0
        self.current_time: float = 0.0

        # Threading and queueing infrastructure
        self.display_queue: queue.Queue = queue.Queue(maxsize=self.config.DISPLAY_QUEUE_SIZE)
        self.processing_queue: queue.Queue = queue.Queue(maxsize=self.config.PROCESSING_QUEUE_SIZE)
        self.ui_update_queue: queue.Queue = queue.Queue(maxsize=self.config.UI_UPDATE_QUEUE_SIZE)

        self.decoder_thread: Optional[threading.Thread] = None
        self.display_thread: Optional[threading.Thread] = None
        self.processing_thread: Optional[threading.Thread] = None
        
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()

        # state lock for thread safety
        self._state_lock = threading.RLock()  # Use RLock for re-entrant access
        self._state_condition = threading.Condition(self._state_lock)
        self._is_playing = False

        self.current_fps: float = 0.0
        self.processing_latency: float = 0.0
        self._frame_count: int = 0
        self._frame_count_start_time: float = time.time()

    def open(self, path):
        """Opens a video file, sets up streams, and starts the decoder thread."""
        self.cleanup()  # Ensure previous resources are released

        try:
            self.container = av.open(path)
            self.video_stream = self.container.streams.video[0]
            self.fps = self.video_stream.average_rate
            
            # Attempt to enable hardware acceleration
            try:
                self.video_stream.codec_context.thread_count = 0  # Auto-detect threads
            except Exception as e:
                logger.warning(f"Could not set thread count: {e}")

            self.stop_event.clear()
            self.pause_event.clear()

            # Start the decoding process
            self.decoder_thread = threading.Thread(target=self._decoder_loop, daemon=True)
            self.decoder_thread.start()

        except Exception as e:
            logger.error(f"Error opening video file with PyAV: {e}")
            self.cleanup()
            raise

    def open_camera(self, camera_index=0):
        """Opens a camera device for live video capture."""
        self.cleanup()  # Ensure previous resources are released
        self.is_camera = True  # New flag to indicate camera input

        try:
            # Platform-specific camera device configuration
            system = platform.system()
            if system == 'Windows':
                # We're not getting the camera name automatically right now, to get it, run ffmpeg -list_devices true -f dshow -i dummy
                self.container = av.open(f'video=LUMIX Webcam Software', format='dshow')
            elif system == 'Darwin':
                self.container = av.open(f'{camera_index}:', format='avfoundation')
            else:  # Linux
                self.container = av.open(f'/dev/video{camera_index}', format='v4l2')

            # Get video stream and FPS
            self.video_stream = self.container.streams.video[0]
            try:
                self.fps = float(self.video_stream.average_rate)
            except:
                self.fps = 30.0  # Default FPS if unavailable

            # Hardware acceleration setup
            try:
                self.video_stream.codec_context.thread_count = 0
            except Exception as e:
                logger.warning(f"Could not set thread count: {e}")

            self.stop_event.clear()
            self.pause_event.clear()

            # Start decoding thread
            self.decoder_thread = threading.Thread(target=self._decoder_loop, daemon=True)
            self.decoder_thread.start()

        except Exception as e:
            logger.error(f"Error opening camera with PyAV: {e}")
            self.cleanup()
            raise

    def play(self):
        """Starts or resumes playback."""
        if not self.container:
            return

        with self._state_condition:
            if self.pause_event.is_set():
                self.pause_event.clear()
            
            if not self._is_playing:
                self._is_playing = True
                self._state_condition.notify_all()  # Wake up waiting threads
                
                # Start consumer threads only once
                if not self.display_thread or not self.display_thread.is_alive():
                    self.display_thread = threading.Thread(target=self._display_loop, daemon=True)
                    self.display_thread.start()
                
                if self.frame_callback and (not self.processing_thread or not self.processing_thread.is_alive()):
                    self.processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
                    self.processing_thread.start()

    def pause(self):
        """Pauses video playback."""
        with self._state_condition:
            self.pause_event.set()
            self._state_condition.notify_all()

    def is_playing(self):
        """Returns True if the video is currently playing."""
        with self._state_lock:
            return self._is_playing and not self.pause_event.is_set()

    def stop(self):
        """Stops video playback and cleans up resources."""
        self.cleanup()

    def _decoder_loop(self):
        """Decodes frames and pushes them as NumPy arrays to consumer queues."""
        frame_delay = 1.0 / self.fps if self.fps > 0 else 1/30.0
        next_frame_time = time.time()

        for frame in self.container.decode(video=0):
            if self.stop_event.is_set():
                break
            
            while self.pause_event.is_set():
                if self.stop_event.is_set():
                    break
                time.sleep(0.01)

            try:
                # Decode directly to a NumPy array
                frame_np = frame.to_ndarray(format='rgb24')
                self.current_time = frame.pts * self.video_stream.time_base

                # Push NumPy array to queues (non-blocking)
                try:
                    self.display_queue.put_nowait(frame_np)
                except queue.Full:
                    # Drop frames if display can't keep up
                    pass
                    
                if self.frame_callback:
                    try:
                        self.processing_queue.put_nowait(frame_np)
                    except queue.Full:
                        # Processing queue is full. Drop the oldest frame to make space for the newest one.
                        logger.warning("Processing queue full; dropping oldest frame to prioritize recent data.")
                        try:
                            # Remove the oldest frame.
                            self.processing_queue.get_nowait()
                            # Add the new frame.
                            self.processing_queue.put_nowait(frame_np)
                        except (queue.Empty, queue.Full):
                            # This is a defensive catch for rare race conditions.
                            # If it occurs, this new frame is simply dropped.
                            pass

                # More precise timing
                next_frame_time += frame_delay
                sleep_time = next_frame_time - time.time()
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    # We're behind, reset timing
                    next_frame_time = time.time()
                    
            except Exception as e:
                logger.error(f"Decoder loop error: {e}")
                break
        
        with self._state_condition:
            self._is_playing = False
            self._state_condition.notify_all()

    def _display_loop(self):
        """Displays frames from NumPy arrays in the display queue."""
        last_panel_size = (0, 0)
        
        while not self.stop_event.is_set():
            try:
                frame_np = self.display_queue.get(timeout=0.5)
                
                # Check for sentinel value (cleanup signal)
                if frame_np is None:
                    break

                # Cache panel dimensions to avoid repeated winfo calls
                panel_w, panel_h = self.video_panel.winfo_width(), self.video_panel.winfo_height()
                
                if panel_w > 1 and panel_h > 1:
                    # Only resize if dimensions changed or first time
                    if (panel_w, panel_h) != last_panel_size:
                        last_panel_size = (panel_w, panel_h)
                    
                    # Use faster interpolation
                    resized_frame = cv2.resize(frame_np, (panel_w, panel_h), interpolation=cv2.INTER_NEAREST)
                else:
                    resized_frame = frame_np

                # Create image more efficiently
                img = Image.fromarray(resized_frame, 'RGB')
                photo = ImageTk.PhotoImage(img)
                
                # Queue UI update instead of direct access
                try:
                    self.ui_update_queue.put_nowait(photo)
                except queue.Full:
                    pass  # Drop frame if UI update queue is full
            except queue.Empty:
                with self._state_lock:
                    if not self._is_playing and not self.pause_event.is_set():
                        break
            except Exception as e:
                logger.error(f"Display loop error: {e}")
                break
    
    def process_ui_updates(self):
        """Process pending UI updates from worker threads. Call this from main thread."""
        try:
            while True:
                photo = self.ui_update_queue.get_nowait()
                self._update_display(photo)
        except queue.Empty:
            pass
        except Exception as e:
            logger.error(f"UI update processing error: {e}")

    def _update_display(self, photo):
        """Update display in main thread."""
        self.video_panel.config(image=photo)
        self.video_panel.image = photo
    
    def _processing_loop(self):
        """Processes NumPy frames from the processing queue."""
        while not self.stop_event.is_set():
            try:
                frame_rgb = self.processing_queue.get(timeout=0.5)
                
                # Check for sentinel value (cleanup signal)
                if frame_rgb is None:
                    break
                
                # Update FPS counter
                self._frame_count += 1
                elapsed_time = time.time() - self._frame_count_start_time
                if elapsed_time >= 1.0:
                    self.current_fps = self._frame_count / elapsed_time
                    self._frame_count = 0
                    self._frame_count_start_time = time.time()
                
                # Convert directly to grayscale
                frame_gray = frame_rgb

                if self.frame_callback:
                    try:
                        self.frame_callback(frame_gray)
                    except Exception as e:
                        logger.error(f"Frame callback error: {e}")

            except queue.Empty:
                if not self._is_playing and not self.pause_event.is_set():
                    self.current_fps = 0
                    break
            except Exception as e:
                logger.error(f"Processing loop error: {e}")
                break

    def get_time(self):
        """Returns the current playback time in seconds."""
        return float(self.current_time)

    def get_fps(self):
        """Returns the video's frames per second."""
        return float(self.fps) if self.fps else 0.0

    def set_position(self, pos):
        """Seeks to a position in the video (fraction 0.0 to 1.0)."""
        if hasattr(self, 'is_camera') and self.is_camera:
            logger.warning("Cannot seek in camera stream")
            return  # Skip seeking for camera input
        if self.container:
            try:
                target_ts = pos * self.container.duration
                self.container.seek(int(target_ts))
                self.current_time = target_ts / av.time_base # Update time immediately
            except Exception as e:
                logger.error(f"Seek error: {e}")

    def get_latency(self):
        """Returns the last measured frame processing latency in seconds."""
        return self.processing_latency

    def get_current_fps(self):
        """Returns the current processing framerate."""
        return self.current_fps

    def _join_thread(self, thread: Optional[threading.Thread], name: str, timeout: float = 2.0) -> None:
        """Joins a thread with a timeout and logs a warning on failure."""
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning(f"{name} thread did not terminate cleanly.")

    def cleanup(self) -> None:
        """Stops all threads and releases video resources."""
        self.is_camera = False  # Reset camera flag
        logger.info("Cleaning up video manager...")
        
        # Atomically stop all operations
        with self._state_condition:
            self._is_playing = False
            self.stop_event.set()
            self._state_condition.notify_all()
        
        # Unblock threads waiting on queues
        for q in [self.display_queue, self.processing_queue]:
            try:
                q.put_nowait(None)
            except queue.Full:
                pass
        
        # Wait for threads to finish
        self._join_thread(self.decoder_thread, "Decoder")
        self._join_thread(self.display_thread, "Display")
        self._join_thread(self.processing_thread, "Processing")
        
        # Safely clear queues
        for q in [self.display_queue, self.processing_queue, self.ui_update_queue]:
            self._clear_queue_safely(q)

        # Close PyAV container
        if self.container:
            try:
                self.container.close()
                logger.info("Video container closed.")
            except Exception as e:
                logger.error(f"Error closing video container: {e}", exc_info=True)
            finally:
                self.container = None
                self.video_stream = None

    def _clear_queue_safely(self, q):
        """Safely clear a queue without holding the mutex too long."""
        try:
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
        except Exception as e:
            logger.error(f"Error clearing queue: {e}")
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()