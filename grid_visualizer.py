import time

from audio import AudioGenerator 
from logger import StructuredLogger

logger = StructuredLogger.get_logger(__name__)

class GridVisualizer:
    def __init__(self, parent_window, grid_canvas, track_manager):
        self.parent_window = parent_window
        self.grid_canvas = grid_canvas
        self.track_manager = track_manager
        self.grid_overlay_timer = None
        self.start_visualization()

    def _update_grid_overlay(self):
        """Re-draw grid lines and flashing notes for the active track."""
        if self.grid_overlay_timer:
            self.parent_window.after_cancel(self.grid_overlay_timer)
            self.grid_overlay_timer = None
     
        start_time = time.time()
        update_interval = 50  # ms
        
        self.grid_canvas.delete("all")

        w = self.grid_canvas.winfo_width()
        h = self.grid_canvas.winfo_height()
        active_track = self.track_manager.get_active_track()
        
        if not active_track or w <= 1 or h <= 1:
            self.parent_window.after(update_interval, self._update_grid_overlay)
            return
        
        gw, gh = active_track.grid_width, active_track.grid_height
        cell_w, cell_h = w//gw, h//gh

        for i in range(1, gw):
            x = i * cell_w
            self.grid_canvas.create_line(x, 0, x, h, fill='white', width=1)
        for j in range(1, gh):
            y = j * cell_h
            self.grid_canvas.create_line(0, y, w, y, fill='white', width=1)

        self.grid_canvas.create_rectangle(0, 0, w, h, outline='white', width=2, fill='')

        if active_track.audio_generator:
            self._draw_active_notes(active_track.audio_generator, gw, gh, cell_w, cell_h)

        self.grid_overlay_timer = self.parent_window.after(update_interval, self._update_grid_overlay)

    def _draw_active_notes(self, audio_generator: AudioGenerator, gw, gh, cell_w, cell_h):
        """Draw active notes for a specific audio generator."""
        if not audio_generator:
            return
            
        current_notes_snapshot = audio_generator.get_current_notes_snapshot()
        note_map_copy = {}
        
        with audio_generator.state_lock:
            note_map_copy = audio_generator.note_map.copy()
        
        for region_index, note in note_map_copy.items():
            if note in current_notes_snapshot:
                velocity = current_notes_snapshot[note]
                intensity = 255 - min(255, velocity * 2)
                color = f"#{255:02x}{intensity:02x}{255:02x}"
                
                row, col = divmod(region_index, gw)
                x1, y1 = col * cell_w, row * cell_h
                x2, y2 = x1 + cell_w, y1 + cell_h
                
                self.grid_canvas.create_rectangle(x1 + 1, y1 + 1, x2 - 1, y2 - 1, fill=color, outline='', width=0)
                
                x_text, y_text = x1 + cell_w // 2, y1 + cell_h // 2
                self.grid_canvas.create_text(x_text, y_text, text=f"N{note}", fill='white', font=('Arial', 8))
                
    def start_visualization(self):
        """Start the grid visualization loop."""
        self._update_grid_overlay()

    def stop_visualization(self):
        """Stop the grid visualization loop."""
        if self.grid_overlay_timer:
            self.grid_canvas.after_cancel(self.grid_overlay_timer)
            self.grid_overlay_timer = None

    def refresh_immediately(self):
        """Force immediate refresh of grid overlay."""
        if self.grid_overlay_timer:
            self.grid_canvas.after_cancel(self.grid_overlay_timer)
        self.grid_overlay_timer = self.grid_canvas.after(0, self._update_grid_overlay)