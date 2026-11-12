#!/usr/bin/env python3
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
import pretty_midi

SEED = 42
N_PER_GENRE = 30
BAR_CHOICES = (8, 16, 24, 32)
OPPOSITE = {"rock": "jazz", "jazz": "rock"}

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def content_hash(pm):
    """Hash of the midi file (instrument, pitch, rounded onset). Catches resaved copies of the same song"""
    items = sorted((int(i.is_drum), int(i.program), n.pitch, round(n.start, 2)) for i in pm.instruments for n in i.notes)
    return hashlib.sha256(repr(items).encode()).hexdigest()


def pick_crop_bars(bpm):
    """How many bars give a 30-60 s excerpt at this tempo? (one bar of 4/4 lasts 240/bpm seconds)"""
    for bars in BAR_CHOICES:
        duration = bars * 240.0 / bpm
        if 30.0 <= duration <= 60.0: # want  30-60s excerpts
            return bars
    return None


def problems_from_inspection(r):
    """Returns a list of errors for choosing valid midi's (empty list returns means valid midi)"""
    if r.get("status") != "Success":
        return ["could not be parsed"]
    probs = []

    if not r.get("constant_tempo"):
        probs.append("tempo changes")

    if not r.get("only_4_4"):
        probs.append("not 4/4 only")

    if r.get("pitched_tracks", 0) < 2:
        probs.append("fewer than 2 pitched tracks (need melody + accompaniment)")

    if r.get("drum_tracks", 0) < 1:
        probs.append("no drum track")

    bars = pick_crop_bars(r["tempo_bpm"]) if r.get("tempo_bpm") else None

    if bars is None:
        probs.append(f"tempo {r.get('tempo_bpm')} BPM: no 30-60 s bar aligned excerpt possible")
    elif r["duration_notes_sec"] < bars * 240.0 / r["tempo_bpm"]:
        probs.append(f"too short for a {bars}-bar excerpt")
    return probs


def suggest_melody_track(pm):
    """
    estimates melody track. melody tends to be monophonic in mid high register with lots of notes and accompanied by chords
    """
    best, best_score = None, -1e9
    for idx, inst in enumerate(pm.instruments):
        if inst.is_drum or len(inst.notes) < 20:
            continue
        notes = sorted(inst.notes, key=lambda n: (n.start, n.pitch))
        overlaps = sum(1 for a, b in zip(notes, notes[1:]) if b.start < a.end - 0.02)
        mono = 1 - overlaps / max(len(notes) - 1, 1) # monophonic score
        mean_pitch = np.mean([n.pitch for n in notes])
        mono_score = 2 * mono
        pitch_score = (mean_pitch - 40) / 60.0 #bcs midi higher registers have higher pitch (>40) punishes low register, and divide by 60 (middle c) to normalise
        note_score = min(len(notes), 400) / 400.0 #reward tracks with more notes
        score = mono_score + pitch_score + note_score
        if score > best_score:
            best, best_score = idx, score
    return best


def propose_crop(pm, melody_idx, bpm, n_bars):
    """
    picks most active n_bars window where melody plays in >=75% of bars.
    Pick the most active n_bars window in which the melody plays in >=75% of bars.
    """
    bar_duration = 240.0 / bpm
    total_bars = int(pm.get_end_time() // bar_duration)
    density = np.zeros(total_bars)
    melody_on = np.zeros(total_bars, dtype=bool) #flag list that shows if melody playing in bars
    for i, inst in enumerate(pm.instruments):
        for note in inst.notes:
            bar = int(note.start // bar_duration)
            if bar < total_bars:
                density[bar] += 1
                if i == melody_idx:
                    melody_on[bar] = True
    best, best_score = None, -1
    for window_start in range(0, total_bars - n_bars + 1, 4):
        w = slice(window_start, window_start + n_bars)
        if melody_on[w].mean() >= 0.75 and density[w].sum() > best_score:
            best, best_score = window_start, density[w].sum()
    return (best, "ok") if best is not None else (None, "no window where melody is active in >=75% of bars")


def main(args):
    # index all midi files under the specified midi_root folder
    index = {p.name: p for p in Path(args.midi_root).rglob("*") if p.suffix.lower() in (".mid", ".midi")}
    rng = np.random.default_rng(SEED)
    selected, excluded = [], []

    
    for genre, csv_path in (("rock", args.rock_csv), ("jazz", args.jazz_csv)):
        df = pd.read_csv(csv_path)
        
        # Ensure every composition has a unique ID based on its filename if not already present
        df["composition_id"] = df["composition_id"] if "composition_id" in df.columns else df["filename"].str.rsplit(".", n=1).str[0]
        
        # Shuffle the rows first using seed 42, then process sequentially
        df = df.iloc[rng.permutation(len(df))].reset_index(drop=True)
        seen_comp, seen_fp, kept = set(), set(), []
        
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            reasons = problems_from_inspection(row_dict)
            
            # checks for data quality, duplicate IDs, or missing files on disk
            if not reasons and row_dict["composition_id"] in seen_comp: 
                reasons.append("duplicate composition_id")
            if not reasons and row_dict["filename"] not in index:       
                reasons.append("midi file not found under --midi_root")
            if not reasons and len(kept) >= N_PER_GENRE:
                excluded.append(dict(genre=genre, filename=row_dict["filename"], reason="eligible but not needed (30 already chosen)"))
                continue
                
            # If basic checks pass, analyze the actual MIDI file content
            if not reasons:
                path = index[row_dict["filename"]]
                pm = pretty_midi.PrettyMIDI(str(path))
                ch = content_hash(pm)
                
                if ch in seen_fp:
                    reasons.append("duplicate musical content")
                    
                mel = suggest_melody_track(pm)
                n_bars = pick_crop_bars(row_dict["tempo_bpm"])
                
                if not reasons:
                    start, note = propose_crop(pm, mel, row_dict["tempo_bpm"], n_bars) if mel is not None else (None, "no melody candidate")
                    if start is None:
                        reasons.append(note)
                        
            # If any check failed, log the exclusion reason and skip
            if reasons:
                excluded.append(dict(genre=genre, filename=row_dict["filename"], reason="; ".join(reasons)))
                continue
                
            # Record the successful composition
            seen_comp.add(row_dict["composition_id"])
            seen_fp.add(ch)
            bar_seconds = 240.0 / row_dict["tempo_bpm"]
            
            kept.append(dict(
                case_id="", 
                source_id=row_dict["composition_id"], 
                source_dataset=args.source_dataset,
                title="", artist="",                                   
                source_style=genre, 
                target_style=OPPOSITE[genre], 
                split="",
                midi_file=row_dict["filename"],
                file_path=row_dict.get("filename", f"data/{genre}/{row_dict['filename']}"),
                sha256=sha256(path),
                tempo_bpm=row_dict["tempo_bpm"], 
                time_signature="4/4",
                total_bars_in_file=int(row_dict["duration_notes_sec"] // bar_seconds),
                melody_track=int(mel), 
                melody_track_name=pm.instruments[mel].name,
                melody_program=int(pm.instruments[mel].program),
                crop_start_bar=int(start), 
                crop_bars=int(n_bars),
                crop_start_sec=round(start * bar_seconds, 3), 
                crop_end_sec=round((start + n_bars) * bar_seconds, 3),
            ))
            
        if len(kept) < N_PER_GENRE:
            print(f"WARNING: only {len(kept)} eligible {genre} files (need {N_PER_GENRE}). Add more midis.")
            
        # Split assignment: 50% train (~15), ~16.6% val (~5), rest test (~10)
        total_kept = len(kept)
        train_count = round(total_kept * 0.5)
        val_count = round(total_kept / 6)
        
        for index_idx, record in enumerate(kept):
            if index_idx < train_count:
                record["split"] = "train"
            elif index_idx < train_count + val_count:
                record["split"] = "val"
            else:
                record["split"] = "test"
                
            record["case_id"] = f"{genre}_{index_idx + 1:03d}"
            
        selected += kept

    # Export final dataset manifest, exclusions log, and verification checksums
    manifest_df = pd.DataFrame(selected)
    manifest_df.to_csv(args.out, index=False, escapechar='\\')
    
    pd.DataFrame(excluded).to_csv(Path(args.out).with_name("manifest_exclusions.csv"), index=False)
    
    frozen_metadata = dict(
        seed=SEED, 
        n_total=len(manifest_df), 
        per_genre_split=manifest_df.groupby(["source_style", "split"]).size().to_dict().__repr__(),
        manifest_sha256=sha256(args.out)
    )
    Path(args.out).with_name("manifest_frozen.json").write_text(json.dumps(frozen_metadata, indent=2))
    
    # Print execution summary reports to console
    print(manifest_df.groupby(["source_style", "split"]).size().unstack())
    print(f"\nExcluded {len(excluded)} files; reasons:")
    print(pd.DataFrame(excluded).reason.str.slice(0, 60).value_counts().head(10))
    print(f"\nSaved {args.out}, manifest_exclusions.csv, manifest_frozen.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    # Pointing defaults directly to your data folder layout
    ap.add_argument("--rock_csv", default="data/rock_dataset.csv")
    ap.add_argument("--jazz_csv", default="data/jazz_dataset.csv")
    ap.add_argument("--midi_root", default="data", help="folder containing the .mid files (searched recursively)")
    ap.add_argument("--source_dataset", default="Lakh MIDI Clean Dataset")
    ap.add_argument("--out", default="dataset_manifest.csv")
    main(ap.parse_args())







