
SCALES = dict(sorted({
    # Major scales and modes
    "Major": [0, 2, 4, 5, 7, 9, 11],
    "Dorian": [0, 2, 3, 5, 7, 9, 10],
    "Phrygian": [0, 1, 3, 5, 7, 8, 10],
    "Lydian": [0, 2, 4, 6, 7, 9, 11],
    "Mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "Locrian": [0, 1, 3, 5, 6, 8, 10],
    
    # Minor scales
    "Minor": [0, 2, 3, 5, 7, 8, 10],
    "Harmonic Minor": [0, 2, 3, 5, 7, 8, 11],
    "Melodic Minor": [0, 2, 3, 5, 7, 9, 11],
    
    # Pentatonic scales
    "Pentatonic Major": [0, 2, 4, 7, 9],
    "Pentatonic Minor": [0, 3, 5, 7, 10],
    "Egyptian": [0, 2, 5, 7, 10],
    "Chinese": [0, 4, 6, 7, 11],
    "Japanese": [0, 1, 5, 7, 8],
    "Hirajoshi": [0, 2, 3, 7, 8],
    "Iwato": [0, 1, 5, 6, 10],
    "Kumoi": [0, 2, 3, 7, 9],
    "Pelog": [0, 1, 3, 7, 8],
    
    # Blues and jazz scales
    "Blues": [0, 3, 5, 6, 7, 10],
    "Blues Major": [0, 2, 3, 4, 7, 9],
    "Bebop Major": [0, 2, 4, 5, 7, 8, 9, 11],
    "Bebop Minor": [0, 2, 3, 5, 7, 8, 9, 10],
    "Bebop Dominant": [0, 2, 4, 5, 7, 9, 10, 11],
    
    # Exotic and world scales
    "Hungarian": [0, 2, 3, 6, 7, 8, 11],
    "Hungarian Minor": [0, 2, 3, 6, 7, 8, 11],
    "Hungarian Major": [0, 3, 4, 6, 7, 9, 10],
    "Gypsy": [0, 1, 4, 5, 7, 8, 11],
    "Persian": [0, 1, 4, 5, 6, 8, 11],
    "Jewish": [0, 1, 4, 5, 7, 8, 10],
    "Enigmatic": [0, 1, 4, 6, 8, 10, 11],
    "Neapolitan Minor": [0, 1, 3, 5, 7, 8, 11],
    "Neapolitan Major": [0, 1, 3, 5, 7, 9, 11],
    
    # Whole tone and diminished
    "Whole Tone": [0, 2, 4, 6, 8, 10],
    "Half-Whole Diminished": [0, 1, 3, 4, 6, 7, 9, 10],
    "Whole-Half Diminished": [0, 2, 3, 5, 6, 8, 9, 11],
    
    # Altered and augmented scales
    "Altered": [0, 1, 3, 4, 6, 8, 10],
    "Augmented": [0, 3, 4, 7, 8, 11],
    "Lydian Augmented": [0, 2, 4, 6, 8, 9, 11],
    "Lydian Dominant": [0, 2, 4, 6, 7, 9, 10],
    
    # Indian/Raga scales
    "Raga Malkauns": [0, 3, 5, 8, 10],
    
    # Other modal variations
    "Lydian Minor": [0, 2, 4, 6, 7, 8, 10],
    "Mixolydian b6": [0, 2, 4, 5, 7, 8, 10],
    "Locrian #2": [0, 2, 3, 5, 6, 8, 10],
    
    # Symmetric scales
    "Chromatic": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
    "Tritone": [0, 1, 4, 6, 7, 10],
    "Two-Semitone Tritone": [0, 1, 2, 6, 7, 8],
    
    # Ecclesiastical modes (additional)
    "Hypophrygian": [0, 2, 4, 5, 6, 9, 10],
    "Hypomixolydian": [0, 1, 3, 5, 6, 8, 9],
    
    # Modern/contemporary scales
    "Prometheus": [0, 2, 4, 6, 9, 10],
    "Scriabin": [0, 1, 4, 7, 9],
    "Messiaen Mode 3": [0, 2, 3, 4, 6, 7, 8, 10, 11],
    "Messiaen Mode 4": [0, 1, 2, 5, 6, 7, 8, 11],
    "Messiaen Mode 5": [0, 1, 5, 6, 7, 11],
    "Messiaen Mode 6": [0, 2, 4, 5, 6, 8, 10, 11],
    "Messiaen Mode 7": [0, 1, 2, 3, 5, 6, 7, 8, 9, 11],
    
    # Additional exotic scales
    "Eight Tone Spanish": [0, 1, 3, 4, 5, 6, 8, 10],
    "Purvi Theta": [0, 1, 4, 6, 7, 8, 11],
    "Todi Theta": [0, 1, 3, 6, 7, 8, 11],
    "Marva Theta": [0, 1, 4, 6, 7, 9, 11],
    "Ahir Bhairav": [0, 1, 4, 5, 7, 9, 10],
    
}.items()))



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