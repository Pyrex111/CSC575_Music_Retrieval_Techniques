#!/usr/bin/env python3
import pandas as pd
from pathlib import Path
import pretty_midi

def verify_all_excerpts(manifest_csv="data/excerpt_manifest.csv"):
    df = pd.read_csv(manifest_csv)
    
    passed_count = 0
    failed_count = 0
    
    print(f"Verifying {len(df)} excerpt files...\n" + "-"*50)
    
    for _, row in df.iterrows():
        case_id = row["case_id"]
        excerpt_path = row["excerpt_path"]
        expected_bpm = float(row["tempo_bpm"])
        expected_bars = int(row["crop_bars"])
        

        expected_duration = expected_bars * (240.0 / expected_bpm)
        
        errors = []
        
        # Check if file exists on disk
        if not excerpt_path or not Path(excerpt_path).is_file():
            failed_count += 1
            print(f"{case_id}: File missing from disk ({excerpt_path})")
            continue
            
        try:
            pm = pretty_midi.PrettyMIDI(excerpt_path)
            
            # should hv instruments
            if not pm.instruments:
                errors.append("File has zero instruments")
            
            # check duration
            actual_duration = pm.get_end_time()
            if actual_duration > expected_duration + 0.5:
                errors.append(f"Too long: {actual_duration:.2f}s (expected ~{expected_duration:.2f}s)")
            elif actual_duration < expected_duration * 0.5:
                errors.append(f"Suspiciously short: {actual_duration:.2f}s")
                
            # should start at 0.0s
            all_notes = [note for inst in pm.instruments for note in inst.notes]
            if all_notes:
                earliest_start = min(note.start for note in all_notes)
                if earliest_start > 0.2:
                    errors.append(f"First note starts late at {earliest_start:.2f}s (expected near 0.0s)")
            else:
                errors.append("Contains zero notes across all instruments")
                
            if errors:
                failed_count += 1
                print(f"{case_id} FAILED checks:")
                for err in errors:
                    print(f"    - {err}")
            else:
                passed_count += 1
                print(f"{case_id}: OK (Duration: {actual_duration:.2f}s, Instruments: {len(pm.instruments)})")
                
        except Exception as e:
            failed_count += 1
            print(f"{case_id}: Corrupted MIDI or parse error ({e})")
            
    print("-"*50)
    print(f"Verification Complete: {passed_count} passed, {failed_count} failed.")

if __name__ == "__main__":
    verify_all_excerpts()
