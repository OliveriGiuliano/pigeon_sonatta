import av
import tkinter as tk
from PIL import Image, ImageTk
import threading
import queue
import time
import numpy as np
import cv2

# Constants for queue sizes to manage memory usage
DISPLAY_QUEUE_SIZE = 20
PROCESSING_QUEUE_SIZE = 200

class VideoManager:
    """
    Manages video playback using PyAV (FFmpeg bindings) in a unified pipeline.
    It handles decoding, display, and frame processing in separate threads for
    better performance and synchronization.
    """
    def __init__(self, video_panel, frame_callback=None):
        """
        Initializes the VideoManager.

        Args:
            video_panel (tk.Widget): The Tkinter Label or widget to display video frames.
            frame_callback (function, optional): A callback function to process video frames.
        """
        self.video_panel = video_panel
        self.frame_callback = frame_callback

        # PyAV and video state
        self.container = None
        self.video_stream = None
        self.fps = 0 # original video fps
        self.current_time = 0.0

        # Threading and queueing infrastructure
        self.display_queue = queue.Queue(maxsize=DISPLAY_QUEUE_SIZE)
        self.processing_queue = queue.Queue(maxsize=PROCESSING_QUEUE_SIZE)

        self.decoder_thread = None
        self.display_thread = None
        self.processing_thread = None

        self.stop_event = threading.Event()
        self.pause_event = threading.Event()

        self._is_playing = False

        self.current_fps = 0 #fps of our video display, depends on performance
        self.processing_latency = 0.0
        self._frame_count = 0
        self._frame_count_start_time = time.time()

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
                print(f"Could not set thread count: {e}")

            self.stop_event.clear()
            self.pause_event.clear()

            # Start the decoding process
            self.decoder_thread = threading.Thread(target=self._decoder_loop, daemon=True)
            self.decoder_thread.start()

        except av.AVError as e:
            print(f"Error opening video file with PyAV: {e}")
            self.cleanup()
            raise

    def play(self):
        """Starts or resumes playback."""
        if not self.container:
            return

        if self.pause_event.is_set(): # Resuming from pause
            self.pause_event.clear()
        
        if not self._is_playing:
            self._is_playing = True
            # Start consumer threads only once
            if not self.display_thread or not self.display_thread.is_alive():
                self.display_thread = threading.Thread(target=self._display_loop, daemon=True)
                self.display_thread.start()
            
            if self.frame_callback and (not self.processing_thread or not self.processing_thread.is_alive()):
                self.processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
                self.processing_thread.start()

    def pause(self):
        """Pauses video playback."""
        self.pause_event.set()

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
                        # Drop frames if processing can't keep up
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
                print(f"Decoder loop error: {e}")
                break
        
        self._is_playing = False

    def _display_loop(self):
        """Displays frames from NumPy arrays in the display queue."""
        last_panel_size = (0, 0)
        
        while not self.stop_event.is_set():
            try:
                frame_np = self.display_queue.get(timeout=0.5)

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
                
                # Update UI in main thread
                self.video_panel.after_idle(lambda p=photo: self._update_display(p))

            except queue.Empty:
                if not self._is_playing and not self.pause_event.is_set():
                    break
            except Exception as e:
                print(f"Display loop error: {e}")
                break

    def _update_display(self, photo):
        """Update display in main thread."""
        self.video_panel.config(image=photo)
        self.video_panel.image = photo
    
    def _processing_loop(self):
        """Processes NumPy frames from the processing queue."""
        while not self.stop_event.is_set():
            try:
                # The queue now contains the frame and no timestamp
                frame_rgb = self.processing_queue.get(timeout=0.5)
                
                # Update FPS counter
                self._frame_count += 1
                elapsed_time = time.time() - self._frame_count_start_time
                if elapsed_time >= 1.0:
                    self.current_fps = self._frame_count / elapsed_time
                    self._frame_count = 0
                    self._frame_count_start_time = time.time()
                
                # Convert directly to grayscale
                frame_gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)

                if self.frame_callback:
                    self.frame_callback(frame_gray)

            except queue.Empty:
                if not self._is_playing and not self.pause_event.is_set():
                    self.current_fps = 0
                    break
            except Exception as e:
                print(f"Processing loop error: {e}")
                break

    def get_time(self):
        """Returns the current playback time in seconds."""
        return float(self.current_time)

    def get_fps(self):
        """Returns the video's frames per second."""
        return float(self.fps) if self.fps else 0.0

    def is_playing(self):
        """Returns True if the video is currently playing."""
        return self._is_playing and not self.pause_event.is_set()

    def set_position(self, pos):
        """Seeks to a position in the video (fraction 0.0 to 1.0)."""
        if self.container:
            try:
                target_ts = pos * self.container.duration
                self.container.seek(int(target_ts))
                self.current_time = target_ts / av.time_base # Update time immediately
            except Exception as e:
                print(f"Seek error: {e}")

    def get_latency(self):
        """Returns the last measured frame processing latency in seconds."""
        return self.processing_latency

    def get_current_fps(self):
        """Returns the current processing framerate."""
        return self.current_fps

    def cleanup(self):
        """Stops all threads and releases video resources."""
        self._is_playing = False
        self.stop_event.set()
        
        # Wait for threads to finish
        if self.decoder_thread and self.decoder_thread.is_alive():
            self.decoder_thread.join(timeout=1.0)
        if self.display_thread and self.display_thread.is_alive():
            self.display_thread.join(timeout=1.0)
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=1.0)

        # Clear queues
        with self.display_queue.mutex: self.display_queue.queue.clear()
        with self.processing_queue.mutex: self.processing_queue.queue.clear()

        if self.container:
            self.container.close()
            self.container = None
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()