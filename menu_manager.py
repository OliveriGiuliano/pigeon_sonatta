import tkinter as tk

import pygame.midi 

from logger import StructuredLogger

logger = StructuredLogger.get_logger(__name__)

class MenuManager:
    def __init__(self, parent_window, video_controller, audio_system_manager):
        self.parent_window = parent_window
        self.video_controller = video_controller
        self.audio_system_manager = audio_system_manager
        self.midi_device_menu = None
        self._create_menu()

    def _create_menu(self):
        menubar = tk.Menu(self.parent_window)
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        for label in ["New Project", "Open Project", "Save Project", "Save Project As", None, "Exit"]:
            if label:
                file_menu.add_command(label=label, command=self._menu_action)
            else:
                file_menu.add_separator()
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Input menu
        input_menu = tk.Menu(menubar, tearoff=0)
        input_menu.add_command(label="Video File", command=self._on_open_video_menu)
        input_menu.add_command(label="Camera", command=self._on_open_camera_menu)
        input_menu.add_command(label="Input Settings", command=self._menu_action)
        menubar.add_cascade(label="Input", menu=input_menu)
        
        # Output menu
        output_menu = tk.Menu(menubar, tearoff=0)
        self.midi_device_menu = tk.Menu(output_menu, tearoff=0)
        output_menu.add_cascade(label="Virtual MIDI Port", menu=self.midi_device_menu)
        # Populate the menu
        self._populate_midi_devices()
        output_menu.add_command(label="Save MIDI File", command=self._menu_action)
        output_menu.add_command(label="Record MIDI", command=self._menu_action)
        output_menu.add_separator()
        output_menu.add_command(label="Audio Device", command=self._menu_action)
        menubar.add_cascade(label="Output", menu=output_menu)
        
        # Presets menu
        presets_menu = tk.Menu(menubar, tearoff=0)
        presets_menu.add_command(label="Load Preset", command=self._menu_action)
        presets_menu.add_command(label="Save Preset", command=self._menu_action)
        presets_menu.add_command(label="Manage Presets", command=self._menu_action)
        presets_menu.add_separator()
        presets_menu.add_command(label="Factory Reset", command=self._menu_action)
        menubar.add_cascade(label="Presets", menu=presets_menu)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Show Visual Feedback", command=self._menu_action)
        view_menu.add_command(label="Show Filter Preview", command=self._menu_action)
        view_menu.add_command(label="Fullscreen Video", command=self._menu_action)
        menubar.add_cascade(label="View", menu=view_menu)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self._menu_action)
        help_menu.add_command(label="Documentation", command=self._menu_action)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.parent_window.config(menu=menubar)

    def _populate_midi_devices(self):
        """Populates the MIDI output device menu."""
        self.midi_device_menu.delete(0, tk.END) # Clear existing entries
        
        if not pygame.midi.get_init():
            pygame.midi.init()

        for i in range(pygame.midi.get_count()):
            device_info = pygame.midi.get_device_info(i)
            if device_info[3] == 1:  # Check if it's an output device
                device_name = f"{i}: {device_info[1].decode()}"
                self.midi_device_menu.add_radiobutton(
                    label=device_name,
                    variable=self.audio_system_manager.selected_midi_device_id,
                    value=i,
                    command=self.audio_system_manager._on_midi_device_change
                )

    def _menu_action(self):
        # Placeholder
        pass

    def _on_open_video_menu(self):
        """Handle video file menu selection."""
        self.video_controller.open_video()

    def _on_open_camera_menu(self):
        """Handle camera menu selection."""
        self.video_controller.open_camera()

    def update_midi_device_menu(self):
        """Update MIDI device menu when devices change."""
        self._populate_midi_devices()