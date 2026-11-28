"""
B0 baseline: instrument substitution (Objective 2, PI1)

Takes each excerpt and changes only the instrument of the accompaniment tracks to the target style's palette.
No note is touched. The melody keeps its original instrument.

  Rock excerpt -> Jazz palette        Jazz excerpt -> Rock palette

Run:
  python b0_baseline.py                          # train + val excerpts (development)
  python b0_baseline.py --cases jazz_001 rock_001
The test split is frozen for the final run, so it is skipped unless you add --include_test.
"""
import argparse
import datetime
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pretty_midi

# General MIDI program numbers (0-based). Edit these to change a palette.
PALETTES = {
    "rock": {"chords": 29,    # Overdriven Guitar
             "bass": 34,      # Electric Bass (pick)
             "drums": 0},     # Standard drum kit
    "jazz": {"chords": 0,     # Acoustic Grand Piano
             "bass": 32,      # Acoustic Bass
             "drums": 32},    # Jazz drum kit (use 0 if your SoundFont has no jazz kit)
}
OPPOSITE = {"rock": "jazz", "jazz": "rock"}

# A non-melody track counts as bass if its instrument is a bass (GM 32-39), its name says bass,
# or its notes are very low (average pitch below this MIDI note number).
BASS_MAX_AVG_PITCH = 50

# Saving a MIDI file rounds times to whole ticks, so allow this much difference (seconds) when comparing.
TOLERANCE = 0.002

# MIDI only has 15 channels for pitched tracks. With more tracks than that, some share a channel
# and a player may use the wrong instrument for them.
MAX_PITCHED_TRACKS = 15


def find_role(inst, is_melody):
    """Decide what a track is: melody, drums, bass or chords."""
    if inst.is_drum:
        return "drums"
    if is_melody:
        return "melody"
    avg_pitch = np.mean([n.pitch for n in inst.notes])
    if 32 <= inst.program <= 39 or "bass" in inst.name.lower() or avg_pitch < BASS_MAX_AVG_PITCH:
        return "bass"
    return "chords"


def make_b0(src_path, out_path, palette, melody_idx):
    """Read the excerpt, change the instrument of every accompaniment track, write the new file."""
    pm = pretty_midi.PrettyMIDI(str(src_path))
    roles = []
    for i, inst in enumerate(pm.instruments):
        role = find_role(inst, i == melody_idx)
        roles.append(role)
        if role != "melody":
            inst.program = palette[role]       # the only change: which instrument plays this track
    pm.write(str(out_path))
    return roles


def note_array(inst):
    """A track's notes as rows of [pitch, velocity, start, end], in a fixed order."""
    notes = sorted(inst.notes, key=lambda n: (n.pitch, round(n.start, 2), round(n.end, 2)))
    return np.array([[n.pitch, n.velocity, n.start, n.end] for n in notes]).reshape(-1, 4)


def same_notes(a, b):
    x, y = note_array(a), note_array(b)
    return (x.shape == y.shape
            and np.array_equal(x[:, :2], y[:, :2])                       # pitch and velocity identical
            and np.allclose(x[:, 2:], y[:, 2:], atol=TOLERANCE, rtol=0))  # start and end times match


def verify(src_path, out_path, palette, melody_idx):
    """Compare the B0 file to its source, track by track. Returns a list of problems (empty = all preserved)."""
    src = pretty_midi.PrettyMIDI(str(src_path))
    out = pretty_midi.PrettyMIDI(str(out_path))
    if len(src.instruments) != len(out.instruments):
        return ["number of tracks changed"]

    problems = []
    for i, (a, b) in enumerate(zip(src.instruments, out.instruments)):
        role = find_role(a, i == melody_idx)
        expected_program = a.program if role == "melody" else palette[role]
        if a.is_drum != b.is_drum:
            problems.append(f"track {i} ({role}): drum flag changed")
        if not same_notes(a, b):
            problems.append(f"track {i} ({role}): notes changed")
        if b.program != expected_program:
            problems.append(f"track {i} ({role}): instrument is {b.program}, expected {expected_program}")

    if abs(src.get_end_time() - out.get_end_time()) > TOLERANCE:
        problems.append("excerpt length changed")
    if not np.allclose(src.get_tempo_changes()[1], out.get_tempo_changes()[1]):
        problems.append("tempo changed")
    return problems


def main(args):
    manifest = pd.read_csv(args.manifest)

    splits = [s.strip() for s in args.splits.split(",")]
    if args.cases:
        manifest = manifest[manifest.case_id.isin(args.cases)]
    else:
        manifest = manifest[manifest.split.isin(splits)]
    if manifest.empty:
        raise SystemExit("No excerpts selected. Check --manifest, --splits and --cases.")
    if (manifest.split == "test").any() and not args.include_test:
        raise SystemExit("The test split is frozen for the final run. Add --include_test only for that run.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log = []
    for _, row in manifest.iterrows():
        target = OPPOSITE[row["source_style"]]
        palette = PALETTES[target]
        out_path = out_dir / f"{row['case_id']}_B0_to_{target}.mid"
        start = time.perf_counter()
        try:
            melody_idx = int(row["excerpt_melody_track"])
            roles = make_b0(row["excerpt_path"], out_path, palette, melody_idx)
            problems = verify(row["excerpt_path"], out_path, palette, melody_idx)
            status, details = ("OK", "") if not problems else ("FAILED", "; ".join(problems))
        except Exception as e:
            roles, status, details = [], "FAILED", f"{type(e).__name__}: {e}"
        warning = ""
        if sum(r != "drums" for r in roles) > MAX_PITCHED_TRACKS:
            warning = "more than 15 pitched tracks: some share a MIDI channel, check playback"
        seconds = round(time.perf_counter() - start, 3)
        print(f"{row['case_id']:>9} -> {target:4} {status} {details} {warning}")
        log.append(dict(case_id=row["case_id"], split=row["split"], source_style=row["source_style"],
                        target_style=target, status=status, problems=details, warning=warning,
                        tracks=len(roles), roles=" ".join(roles), seconds=seconds, output_file=str(out_path)))

    pd.DataFrame(log).to_csv(out_dir / "b0_log.csv", index=False)
    config = dict(date=datetime.datetime.now().isoformat(timespec="seconds"), manifest=args.manifest,
                  palettes=PALETTES, bass_max_avg_pitch=BASS_MAX_AVG_PITCH, tolerance_seconds=TOLERANCE)
    (out_dir / "b0_config.json").write_text(json.dumps(config, indent=2))

    passed = sum(1 for r in log if r["status"] == "OK")
    print(f"\n{passed} of {len(log)} files passed all checks. Log: {out_dir / 'b0_log.csv'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/excerpt_manifest.csv")
    parser.add_argument("--out_dir", default="b0")
    parser.add_argument("--splits", default="train,val", help="comma separated list")
    parser.add_argument("--include_test", action="store_true")
    parser.add_argument("--cases", nargs="*", help="only these case IDs, e.g. jazz_001 rock_001")
    main(parser.parse_args())
