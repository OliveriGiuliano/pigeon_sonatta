# video.py
import tkinter as tk
import vlc
import threading
import time
import atexit
import os
import cv2
import numpy as np

class VideoManager:
    """
    Wraps a python-vlc MediaPlayer to handle video playback under VLC's timing,
    hardware decode, and scaling. Exposes simple controls and timing stats.
    """
    def __init__(self, video_panel, frame_callback=None):
        """
        video_panel: a Tkinter widget (Frame/Label/Canvas) to embed VLC video into.
        frame_callback: optional callback function to receive video frames for processing
        """
        # Keep a ref to the widget so we can extract its window handle:
        self.video_panel = video_panel
        self.frame_callback = frame_callback
        self.instance = None
        self.player = None
        self.media = None
        self._is_initialized = False
        self._frame_capture_thread = None
        self._stop_capture = False
        
        # Register cleanup on exit
        atexit.register(self.cleanup)
        
        self._initialize_vlc()

    def _initialize_vlc(self):
        """Initialize VLC with proper error handling and resource management."""
        try:
            # More robust VLC options
            vlc_options = [
                '--no-xlib',
                '--quiet',                     # Reduce VLC logging
                '--no-video-title-show',       # Don't show filename overlay
                '--no-snapshot-preview',       # Disable snapshot preview
                '--no-osd',                    # Disable on-screen display
                '--no-stats',                  # Disable statistics
                '--no-sub-autodetect-file',    # Don't auto-detect subtitles
                '--no-disable-screensaver',    # Don't disable screensaver
                '--avcodec-hw=none',           # Start with software decoding
                '--vout=directx' if os.name == 'nt' else '--vout=x11',  # Platform-specific video output
            ]
            
            self.instance = vlc.Instance(vlc_options)
            if not self.instance:
                raise RuntimeError("Failed to create VLC instance")
                
            self.player = self.instance.media_player_new()
            if not self.player:
                raise RuntimeError("Failed to create VLC media player")
                
            self._set_window_handle()
            self._is_initialized = True
            
        except Exception as e:
            print(f"VLC initialization error: {e}")
            self.cleanup()
            raise

    def _set_window_handle(self):
        """Hook VLC video output into our Tkinter widget with better error handling."""
        if not self.video_panel or not hasattr(self.video_panel, 'winfo_id'):
            return
            
        try:
            # Wait for widget to be mapped
            self.video_panel.update_idletasks()
            hwnd = self.video_panel.winfo_id()
            
            # Platform-specific window handle setting
            if tk.sys.platform.startswith('win'):
                self.player.set_hwnd(hwnd)
            elif tk.sys.platform.startswith('linux'):
                self.player.set_xwindow(hwnd)
            elif tk.sys.platform == 'darwin':
                self.player.set_nsobject(hwnd)
                
        except Exception as e:
            print(f"Window handle error: {e}")

    def set_video_path(self, path):
        """Store video path for frame extraction."""
        self._current_video_path = path

    def open(self, path):
        """Load a file (or stream) into VLC with proper cleanup."""
        if not self._is_initialized:
            self._initialize_vlc()
            
        try:
            # Stop and cleanup previous media
            if self.player:
                self.player.stop()
                
            # Release previous media
            if self.media:
                self.media.release()
                
            # Create new media
            self.media = self.instance.media_new(path)
            if not self.media:
                raise RuntimeError(f"Failed to create media from: {path}")
                
            self.player.set_media(self.media)
            
            # Better priming approach - wait for media to be parsed
            self._prime_player()
            
        except Exception as e:
            print(f"Media loading error: {e}")
            raise

    def _prime_player(self):
        """Prime the player with better synchronization."""
        def _prime():
            try:
                # Start playback
                self.player.play()
                
                # Wait for player to actually start
                max_wait = 50  # 5 seconds max
                wait_count = 0
                while not self.player.is_playing() and wait_count < max_wait:
                    time.sleep(0.1)
                    wait_count += 1
                
                if self.player.is_playing():
                    # Let it play for a moment to establish video context
                    time.sleep(0.2)
                    # Then pause
                    self.player.pause()
                else:
                    print("Warning: Player failed to start")
                    
            except Exception as e:
                print(f"Player priming error: {e}")
        
        threading.Thread(target=_prime, daemon=True).start()

    def play(self):
        if self.player and self._is_initialized:
            self.player.play()
            self._start_frame_capture()

    def pause(self):
        if self.player and self._is_initialized:
            self.player.pause()
            self._stop_frame_capture()

    def stop(self):
        if self.player and self._is_initialized:
            self.player.stop()
            self._stop_frame_capture()

    def get_time(self):
        """Return current playback time in seconds."""
        if not self.player or not self._is_initialized:
            return 0.0
        try:
            return self.player.get_time() / 1000.0
        except:
            return 0.0

    def get_fps(self):
        """Return the video's native FPS, if known (else 0.0)."""
        if not self.player or not self._is_initialized:
            return 0.0
        try:
            return self.player.get_fps() or 0.0
        except:
            return 0.0

    def is_playing(self):
        if not self.player or not self._is_initialized:
            return False
        try:
            return bool(self.player.is_playing())
        except:
            return False

    def set_position(self, pos):
        """Seek to a fraction [0.0–1.0] of the video."""
        if self.player and self._is_initialized:
            try:
                self.player.set_position(pos)
            except:
                pass

    def set_frame_callback(self, callback):
        """Set callback function to receive video frames."""
        self.frame_callback = callback

    def _start_frame_capture(self):
        """Start frame capture thread for audio processing."""
        if self.frame_callback and not self._frame_capture_thread:
            self._stop_capture = False
            self._frame_capture_thread = threading.Thread(target=self._capture_frames, daemon=True)
            self._frame_capture_thread.start()

    def _stop_frame_capture(self):
        """Stop frame capture thread."""
        self._stop_capture = True
        if self._frame_capture_thread:
            self._frame_capture_thread.join(timeout=1.0)
            self._frame_capture_thread = None

    def _capture_frames(self):
        """Capture frames from VLC for audio processing."""
        if not self.frame_callback:
            return
            
        # Create a VideoCapture object for the same video file
        # This is a workaround since VLC doesn't easily provide frame access
        # Note: This assumes we have access to the video file path
        # In a full implementation, you might want to use VLC's snapshot feature
        # or implement a more sophisticated frame capture mechanism
        
        frame_rate = max(self.get_fps(), 30.0)  # Default to 30 fps if unknown
        frame_interval = 1.0 / frame_rate
        
        while not self._stop_capture and self.is_playing():
            try:
                # For now, we'll use a placeholder frame
                # In a real implementation, you'd capture the actual frame from VLC
                # This could be done using VLC's snapshot feature or by reading
                # the video file directly with OpenCV
                
                # Placeholder: Create a black frame
                # You would replace this with actual frame capture
                if hasattr(self, '_current_video_path') and self._current_video_path:
                    frame = self.get_current_frame_from_file(self._current_video_path)
                    if frame is not None and self.frame_callback:
                        self.frame_callback(frame)
                
                time.sleep(frame_interval)
                
            except Exception as e:
                print(f"Frame capture error: {e}")
                break

    def get_current_frame_from_file(self, video_path):
        """
        Get current frame by reading from video file at current position.
        This is a workaround for VLC frame access limitations.
        """
        if not video_path or not os.path.exists(video_path):
            return None
            
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None
                
            # Get current position as fraction
            current_pos = self.player.get_position()
            if current_pos < 0:
                current_pos = 0
                
            # Get total frames and seek to current position
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            target_frame = int(current_pos * total_frames)
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()
            
            cap.release()
            return frame if ret else None
            
        except Exception as e:
            print(f"Frame extraction error: {e}")
            return None

    def cleanup(self):
        """Thorough cleanup of VLC resources."""
        self._is_initialized = False
        self._stop_frame_capture()
        
        try:
            if self.player:
                self.player.stop()
                self.player.release()
                self.player = None
                
            if self.media:
                self.media.release()
                self.media = None
                
            if self.instance:
                self.instance.release()
                self.instance = None
                
        except Exception as e:
            print(f"Cleanup error: {e}")

    def release(self):
        """Public method to release resources."""
        self.cleanup()

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()