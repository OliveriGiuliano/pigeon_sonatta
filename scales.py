# scales.py
SCALES = {
    "Major": [0, 2, 4, 5, 7, 9, 11],
    "Minor": [0, 2, 3, 5, 7, 8, 10],
    "Pentatonic Major": [0, 2, 4, 7, 9],
    "Pentatonic Minor": [0, 3, 5, 7, 10],
    "Blues": [0, 3, 5, 6, 7, 10],
    "Dorian": [0, 2, 3, 5, 7, 9, 10],
    "Mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "Harmonic Minor": [0, 2, 3, 5, 7, 8, 11],
    "Chromatic": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def get_available_scales():
    """Return list of available scale names."""
    return list(SCALES.keys())

def get_note_names():
    """Return list of note names."""
    return NOTE_NAMES

def generate_scale_notes(root_note, scale_name, note_range):
    """
    Generate scale notes within the given range.
    
    Args:
        root_note (int): MIDI note number for root (0-127)
        scale_name (str): Name of the scale
        note_range (tuple): (min_note, max_note) range
        
    Returns:
        list: MIDI note numbers in the scale within range
    """
    if scale_name not in SCALES:
        scale_name = "Major"
    
    intervals = SCALES[scale_name]
    min_note, max_note = note_range
    scale_notes = []
    
    # Start from the lowest octave that contains notes in our range
    start_octave = (min_note - root_note) // 12
    if (min_note - root_note) % 12 > 0:
        start_octave += 1
    
    octave = start_octave
    while True:
        notes_added = False
        for interval in intervals:
            note = root_note + (octave * 12) + interval
            if min_note <= note <= max_note:
                scale_notes.append(note)
                notes_added = True
            elif note > max_note:
                break
        
        if not notes_added and octave > start_octave:
            break
            
        octave += 1
        if root_note + (octave * 12) > max_note:
            break
    
    return sorted(scale_notes)