import os
import pretty_midi

def inspect_midi_file(file_path):
    """
    Load a single MIDI file and extracts tracks, note counts, tempo, meter, and duration.
    """
    try:
        midi_data = pretty_midi.PrettyMIDI(file_path)
        
        num_tracks = len(midi_data.instruments)
        
        # extract total note count
        total_notes = 0
        for instrument in midi_data.instruments:
            total_notes += len(instrument.notes)
        
        # extract duration
        duration_seconds = midi_data.get_end_time()
        
        # extract temp
        estimated_tempo = midi_data.estimate_tempo()
        
        # extract time signature
        time_signatures = midi_data.time_signature_changes
        if time_signatures:
            ts = time_signatures[0]
            time_signature = f"{ts.numerator}/{ts.denominator}"
        else:
            time_signature = "4/4 (Default)"  # default if not included
            
        return {
            "filename": os.path.basename(file_path),
            "status": "Success",
            "tracks": num_tracks,
            "total_notes": total_notes,
            "duration_sec": round(duration_seconds, 2),
            "tempo_bpm": round(estimated_tempo, 1),
            "time_signature": time_signature
        }
        
    except Exception as e:
        # Catch malformed or corrupted MIDI files gracefully
        return {
            "filename": os.path.basename(file_path),
            "status": f"Error: {str(e)}"
        }

def scan_midi_folder(folder_path):
    """
    Scans a folder for all .mid files and prints their summary.
    """
    print(f"Scanning {folder_path}\n")
    results = []
    
    
    if not os.path.exists(folder_path):
        print(f"Directory not found: {folder_path}.")
        return results

    for file in os.listdir(folder_path):
        if file.lower().endswith(('.mid', '.midi')):
            full_path = os.path.join(folder_path, file)
            info = inspect_midi_file(full_path)
            results.append(info)
            
            
            print(f"File: {info['filename']}")
            print(f"Status: {info['status']}")
            if info['status'] == "Success":
                print(f"  - Tracks: {info['tracks']}")
                print(f"  - Total Notes: {info['total_notes']}")
                print(f"  - Duration: {info['duration_sec']} seconds")
                print(f"  - Tempo: {info['tempo_bpm']} BPM")
                print(f"  - Time Signature: {info['time_signature']}")
            print("-" * 40)
            
    return results

if __name__ == "__main__":
    sample_folder = "./sample_midis"
    scan_midi_folder(sample_folder)
