import numpy as np
import csv
import sys
from pathlib import Path
import mido
import pretty_midi

def inspect_midi_file(file_path):
    path = Path(file_path)
    try:
        rel_path = str(path.relative_to(Path.cwd()))
    except ValueError:
        rel_path = str(path) 

    info = {"filename": path.name, "filepath": rel_path, "status": "Success", "warnings": []}
    try:
        raw = mido.MidiFile(str(path), clip=True)
        pm = pretty_midi.PrettyMIDI(str(path))
    except Exception as e:
        info["status"] = f"Error: {type(e).__name__}: {e}"
        return info

    
    pitched = [i for i in pm.instruments if not i.is_drum and i.notes]
    drums = [i for i in pm.instruments if i.is_drum and i.notes]
    info["raw_midi_tracks"] = len(raw.tracks)
    info["tracks_with_notes"] = len(pitched)+len(drums)
    info["pitched_tracks"] = len(pitched)
    info["drum_tracks"] = len(drums)
    info["total_notes"] = sum(len(i.notes) for i in pm.instruments)

    # extracting tempo
    tempo_events = [] # (tick,bpm)
    for track in raw.tracks:
        tick = 0
        for msg in track:
            tick += msg.time
            if msg.type == "set_tempo":
                tempo_events.append((tick, mido.tempo2bpm(msg.tempo)))
    distinct = sorted({round(b, 2) for _, b in tempo_events})
    info["tempo_changes"] = max(len(distinct)-1, 0)
    if not tempo_events:
        info["tempo_bpm"] = 120.0 #default
        info["warnings"].append("no tempo event in midi;default 120 BPM assumed")
    else:
        first = min(tempo_events, key=lambda e: e[0]) #first tempo in midi file
        info["tempo_bpm"] = round(first[1], 2)
        if len(distinct) > 1:
            info["warnings"].append(f"tempo changes within file: {distinct}")
    info["constant_tempo"] = len(distinct) <= 1

    # time signatures
    sigs = sorted({(m.numerator, m.denominator) for t in raw.tracks for m in t if m.type == "time_signature"})
    info["time_signatures"] = ", ".join(f"{a}/{b}" for a, b in sigs) or "4/4 (default, none stored)"
    if len(sigs) > 1:
        info["warnings"].append("multiple time signatures")
    info["only_4_4"] = (not sigs) or sigs == [(4, 4)]

    # duration
    info["duration_notes_sec"] = round(pm.get_end_time(), 2) #last note
    try:
        info["duration_file_sec"] = round(raw.length, 2) #raw file length that could hv silence as well
    except Exception:
        info["duration_file_sec"] = None
    if info["duration_file_sec"] and abs(info["duration_file_sec"] - info["duration_notes_sec"]) > 1.0:
        info["warnings"].append("file length and last note time differ by >1 s (silence/padding at end)")

    # bars
    if info["constant_tempo"] and info["only_4_4"]:
        info["bars_approx"] = round(info["duration_notes_sec"] / (240.0 / info["tempo_bpm"]), 1)
    else:
        info["bars_approx"] = None
    return info


def scan_midi_folder(folder_path, csv_out=None):
    folder = Path(folder_path)
    if not folder.is_dir():
        print(f"Directory not found: {folder}")
        return []
    results = [inspect_midi_file(p) for p in sorted(folder.rglob("*"))
               if p.suffix.lower() in (".mid", ".midi")]
    for r in results:
        print(f"\nFile: {r['filename']}   [{r['status']}]")
        if r["status"] == "Success":
            print(f"  tracks with notes : {r['tracks_with_notes']} ({r['pitched_tracks']} pitched, {r['drum_tracks']} drum)  | raw MIDI tracks: {r['raw_midi_tracks']}")
            print(f"  total notes       : {r['total_notes']}")
            print(f"  tempo             : {r['tempo_bpm']} BPM constant={r['constant_tempo']}")
            print(f"  time signature    : {r['time_signatures']}")
            print(f"  duration          : {r['duration_notes_sec']} s (last note) / {r['duration_file_sec']} s (file length)  ~{r['bars_approx']} bars")
            for w in r["warnings"]:
                print(f"  WARNING: {w}")
    if csv_out and results:
        keys = sorted({k for r in results for k in r})
        with open(csv_out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in results:
                w.writerow({**r, "warnings": "; ".join(r["warnings"])})
        print(f"\nSaved {csv_out}")
    return results


if __name__ == "__main__":
    scan_midi_folder(sys.argv[1] if len(sys.argv) > 1 else "./sample_midis", csv_out="midi_inspection.csv")
