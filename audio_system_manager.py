import tkinter as tk
from tkinter import messagebox


import pygame.midi 
import pygame.mixer 

from logger import StructuredLogger

logger = StructuredLogger.get_logger(__name__)
class AudioSystemManager:
    def __init__(self, audio_config):
        self.audio_config = audio_config
        self.midi_out = None
        self.selected_midi_device_id = None
        self.device_change_callbacks = []
        self.track_manager = None
        self._initialize_global_audio()

    def _initialize_global_audio(self):
        """Initializes global Pygame systems and the single MIDI output stream."""
        try:
            # Shutdown existing MIDI to allow re-initialization
            if self.midi_out:
                self.midi_out.close()
                self.midi_out = None
            if pygame.midi.get_init():
                pygame.midi.quit()

            pygame.mixer.pre_init(
                frequency=self.audio_config.DEFAULT_FREQUENCY,
                size=-16,
                channels=2,
                buffer=self.audio_config.BUFFER_SIZE
            )
            pygame.mixer.init()
            pygame.midi.init()

            if not self.selected_midi_device_id:
                self.selected_midi_device_id = tk.IntVar(value=pygame.midi.get_default_output_id())
            midi_device_id = self.selected_midi_device_id.get() 
            if midi_device_id == -1:
                logger.warning("No default MIDI output device found.")
                messagebox.showwarning("MIDI Error", "No default MIDI output device was found. Audio generation will be disabled.")
                return
                
            self.midi_out = pygame.midi.Output(midi_device_id)
            device_info = pygame.midi.get_device_info(midi_device_id)
            logger.info(f"Successfully initialized shared MIDI output on device: {device_info[1].decode()}") 
            
        except Exception as e:
            logger.error(f"Global audio initialization error: {e}", exc_info=True)
            messagebox.showerror("Audio Error", f"A critical error occurred initializing the audio system:\n{e}")

    def _on_midi_device_change(self):
        """Handles MIDI output device change and re-initializes audio."""
        selected_id = self.selected_midi_device_id.get()
        logger.info(f"User selected new MIDI device ID: {selected_id}. Re-initializing audio.")

        # Stop all notes on all tracks before switching
        for track in self.track_manager.tracks:
            if track.audio_generator:
                track.audio_generator.stop_all_notes()
        
        # Re-initialize the global audio system with the new device
        self._initialize_global_audio()
        
        # Re-link all existing tracks to the new midi_out object
        for track in self.track_manager.tracks:
            track.midi_out = self.midi_out
            if track.audio_generator:
                track.audio_generator.midi_out = self.midi_out
                track.audio_generator.is_initialized = self.midi_out is not None

    def add_device_change_callback(self, callback):
        """Add callback to be called when MIDI device changes."""
        self.device_change_callbacks.append(callback)

    def get_midi_device_variable(self):
        """Get the MIDI device selection variable."""
        return self.selected_midi_device_id

    def get_available_devices(self):
        """Get list of available MIDI output devices."""
        devices = []
        if pygame.midi.get_init():
            for i in range(pygame.midi.get_count()):
                device_info = pygame.midi.get_device_info(i)
                if device_info[3] == 1:  # Output device
                    devices.append((i, device_info[1].decode()))
        return devices

    def cleanup(self):
        """Clean up audio system."""
        if self.midi_out:
            self.midi_out.close()
            self.midi_out = None
        if pygame.midi.get_init():
            pygame.midi.quit()
        if pygame.mixer.get_init():
            pygame.mixer.quit()