import argparse
from pathlib import Path
import pandas as pd
import pretty_midi
import mido


def pad_to_exact_length(path, bars):
    """makes a midi file end at the end of {bars} bars"""
    mid = mido.MidiFile(str(path))
    target = bars * 4 * mid.ticks_per_beat
    track = mid.tracks[0] # pretty_midi writes the tempo/time-signature track first
    used = sum(m.time for m in track if m.type != "end_of_track")
    track[:] = [m for m in track if m.type != "end_of_track"] + [mido.MetaMessage("end_of_track", time=target - used)]
    mid.save(str(path))

def main(args):
    # load dataset manifest
    manifest = pd.read_csv(args.manifest)
    midi_index = {p.name: p for p in Path(args.midi_root).rglob("*") if p.suffix.lower() in (".mid", ".midi")}
    
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    
    for _, row in manifest.iterrows():
        row_dict = row.to_dict()
        case_id = row_dict["case_id"]
        
        try:
            # Locate the source MIDI file using filepath or filename index
            filepath = row_dict.get("filepath", "")
            src_path = Path(filepath) if Path(filepath).is_file() else midi_index.get(row_dict["midi_file"])
            
            if not src_path or not src_path.is_file():
                raise FileNotFoundError(f"MIDI file not found for {row_dict['midi_file']}")
            
            # calculate start and end time
            bpm = float(row_dict["tempo_bpm"])
            bar_duration = 240.0 / bpm
            t0 = int(row_dict["crop_start_bar"]) * bar_duration
            t1 = t0 + int(row_dict["crop_bars"]) * bar_duration

            # Load the original MIDI file
            pm = pretty_midi.PrettyMIDI(str(src_path))
            
            # new midi object for the exceprt
            excerpt_pm = pretty_midi.PrettyMIDI(resolution=pm.resolution, initial_tempo=bpm)
            excerpt_pm.time_signature_changes = [pretty_midi.TimeSignature(4, 4, 0.0)]

            # slice and shift notes for every instrument
            melody_idx = int(row_dict["melody_track"])   # melody index in the SOURCE file
            kept_indices = []                              # source index of every instrument we keep
            for idx, inst in enumerate(pm.instruments):
                new_inst = pretty_midi.Instrument(program=inst.program, is_drum=inst.is_drum, name=inst.name)
                for note in inst.notes:
                    # keeping notes that fall in window
                    if note.end > t0 and note.start < t1:
                        # Shift the start and end times back by t0 so excerpt starts at 0.0 seconds
                        s = max(note.start, t0) - t0
                        e = min(note.end, t1) - t0
                        
                        if e - s > 0.01:
                            new_inst.notes.append(pretty_midi.Note(note.velocity, note.pitch, s, e))
                
                if new_inst.notes:
                    excerpt_pm.instruments.append(new_inst)
                    kept_indices.append(idx)

            # empty instruments were dropped, so the melody's position may have shifted
            if melody_idx not in kept_indices:
                raise ValueError("melody track has no notes inside the crop window")
            row_dict["excerpt_melody_track"] = kept_indices.index(melody_idx)

            # saving new midi excerpt file
            out_path = out_dir / f"{case_id}.mid"
            excerpt_pm.write(str(out_path))
            pad_to_exact_length(out_path, int(row_dict["crop_bars"]))
            
            row_dict["excerpt_path"] = str(out_path)
            row_dict["status"] = "OK"
            print(f"Successfully cropped: {case_id}.mid")
            
        except Exception as e:
            row_dict["excerpt_path"] = ""
            row_dict["excerpt_melody_track"] = ""
            row_dict["status"] = f"FAILED: {e}"
            print(f"Error cropping {case_id}: {e}")
            
        results.append(row_dict)

    # save the updated manifest tracking new excerpt files
    res_df = pd.DataFrame(results)
    res_df.to_csv(args.out_manifest, index=False)
    print(f"\nDone! Excerpts saved to {out_dir}/ and manifest saved to {args.out_manifest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/dataset_manifest.csv")
    parser.add_argument("--midi_root", default="data", help="folder containing original .mid files")
    parser.add_argument("--out_dir", default="data/excerpts", help="output folder for sliced midis")
    parser.add_argument("--out_manifest", default="data/excerpt_manifest.csv")
    main(parser.parse_args())
