#!/usr/bin/env python3
"""
Chord + phrase annotation (Objective 1, PI4).

  python annotate.py

For every excerpt in the manifest: guesses one chord per bar and a phrase layout, then writes <case>.json next to the excerpt.
"""
import argparse, json
from pathlib import Path
import mido
import numpy as np
import pandas as pd
import pretty_midi

NOTE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# {chord suffix : steps up from the root}
TYPES = {"": [0, 4, 7], "m": [0, 3, 7], "7": [0, 4, 7, 10], "maj7": [0, 4, 7, 11],
         "m7": [0, 3, 7, 10], "dim": [0, 3, 6]}
# every chord other than plain major / minor pays this small penalty, so simple chords win unless the extra note is clearly there
EXTRA_NOTE_PENALTY = 0.05


def bar_features(pm, melody_idx, bar_s, n_bars):
    """For each bar: how much of each pitch class sounds (duration x loudness), and the bass pitch class."""
    hist = np.zeros((n_bars, 12))  # 12 notes for each bar
    bass_hist = np.zeros((n_bars, 12))  # for bass
    lowest = [None] * n_bars  # lowest note for each bar
    for i, inst in enumerate(pm.instruments):
        if inst.is_drum:  # drums no chords
            continue
        role = 0.5 if i == melody_idx else 1.0  # melodies often accompanied w fast notes so count them less
        for n in inst.notes:
            # first and last bar where note plays on
            first, last = int(n.start // bar_s), int(min(n.end, n_bars * bar_s - 1e-9) // bar_s)
            # for every bar that note plays in
            for b in range(max(first, 0), min(last, n_bars - 1) + 1):
                # duration of note
                d = min(n.end, (b + 1) * bar_s) - max(n.start, b * bar_s)
                if d <= 0:
                    continue
                hist[b, n.pitch % 12] += role * d * (n.velocity / 127)  # normalise velocity
                if i != melody_idx:
                    if n.pitch < 60:
                        bass_hist[b, n.pitch % 12] += d
                    if lowest[b] is None or n.pitch < lowest[b]:
                        lowest[b] = n.pitch
    bass = [int(np.argmax(bass_hist[b])) if bass_hist[b].sum() > 0 else (lowest[b] % 12 if lowest[b] is not None else None)
            for b in range(n_bars)]
    return hist, bass


def rank_chords(h, bass_pc):
    """Score every root x chord type against the pitch-class weights h (sums to 1). Higher = better fit."""
    ranked = []
    for root in range(12):
        for suffix, iv in TYPES.items():
            tones = {(root + x) % 12 for x in iv}
            inside = sum(h[p] for p in tones)
            absent = sum(1 for p in tones if h[p] < 0.03)  # chord tones that never sound
            penalty = 0.0 if suffix in ("", "m") else EXTRA_NOTE_PENALTY
            s = inside - 0.8 * (1 - inside) - 0.12 * absent - penalty
            s += 0.25 if bass_pc == root else (0.08 if bass_pc in tones else 0.0)
            ranked.append((round(s, 9), root, suffix))
    # best first; if two chords score exactly the same (e.g. power chords with no third), prefer plain major
    return sorted(ranked, key=lambda r: (-r[0], r[2] != ""))


def guess_chords(pm, melody_idx, bar_s, n_bars):
    """Returns one (root, suffix) per bar, plus the bars where the best and second-best chord were almost tied."""
    hist, bass = bar_features(pm, melody_idx, bar_s, n_bars)
    chords, uncertain, prev = [], [], (0, "")
    for b in range(n_bars):
        total = hist[b].sum()
        if total < 1e-6:  # no pitched notes in this bar: repeat the previous chord
            chords.append(prev)
            uncertain.append(b + 1)
            continue
        ranked = rank_chords(hist[b] / total, bass[b])
        best, second = ranked[0], ranked[1]
        if best[0] - second[0] < 0.05:
            uncertain.append(b + 1)
        prev = (best[1], best[2])
        chords.append(prev)
    return chords, uncertain


def draft_phrases(pm, melody_idx, chord_names, bar_s, n_bars, block=4):
    """Cut into 4-bar blocks: blocks with similar chords + melody rhythm get the same letter."""
    mel = pm.instruments[melody_idx].notes
    sigs = []
    for b0 in range(0, n_bars, block):
        onsets = set()
        for n in mel:
            bar = int(n.start // bar_s)
            if b0 <= bar < b0 + block:
                onsets.add((bar - b0, int(round((n.start - bar * bar_s) / bar_s * 8)) % 8))
        sigs.append((chord_names[b0:b0 + block], onsets))
    labels, firsts = [], {}
    for k, (chords, onsets) in enumerate(sigs):
        best_label, best_sim = None, 0.0
        for lab, (c2, o2) in firsts.items():
            chord_sim = sum(a == b for a, b in zip(chords, c2)) / block
            union = onsets | o2
            rhythm_sim = len(onsets & o2) / len(union) if union else 1.0
            sim = 0.5 * chord_sim + 0.5 * rhythm_sim
            if sim > best_sim:
                best_label, best_sim = lab, sim
        if best_sim >= 0.7:
            labels.append(best_label)
        else:
            lab = chr(ord("A") + len(firsts))
            firsts[lab] = (chords, onsets)
            labels.append(lab)
    return [dict(label=l, start_bar=k * block, bars=block) for k, l in enumerate(labels)]


def excerpt_info(r):
    path = Path(r["excerpt_path"])
    raw = mido.MidiFile(str(path))
    us = [m.tempo for t in raw.tracks for m in t if m.type == "set_tempo"][0]
    bpm = 60e6 / us
    return path, pretty_midi.PrettyMIDI(str(path)), bpm, int(r["crop_bars"]), int(r["excerpt_melody_track"])


def provenance(r):
    g = lambda k: str(r[k]) if k in r and pd.notna(r[k]) and str(r[k]).strip() else "TODO"
    return (f"{g('source_dataset')}; file {g('midi_file')} (sha256 {str(r.get('sha256', ''))[:12]}); title: {g('title')}; "
            f"artist: {g('artist')}; excerpt = source bars {int(r['crop_start_bar']) + 1}-{int(r['crop_start_bar']) + int(r['crop_bars'])}; "
            f"licence: TODO; chords and phrases: automatic estimate, not manually reviewed")


def annotate(r):
    path, pm, bpm, bars, mel = excerpt_info(r)
    bar_s = 240.0 / bpm
    chords, uncertain = guess_chords(pm, mel, bar_s, bars)
    names = [NOTE[root] + suffix for root, suffix in chords]
    ann = dict(schema_version=1, case_id=r["case_id"], source_style=r["source_style"], split=r["split"],
               provenance=provenance(r), midi_path=path.name, melody_track=mel, tempo_bpm=bpm,
               time_signature=[4, 4], bars=bars,
               chords=[dict(root_pc=int(root), intervals=[int(x) for x in TYPES[suffix]]) for root, suffix in chords],
               phrases=draft_phrases(pm, mel, names, bar_s, bars))
    out = path.with_suffix(".json")
    out.write_text(json.dumps(ann, indent=2))
    print(f"{r['case_id']}: wrote {out.name} | progression: {' '.join(names)}")
    print(f"   bars where the chord choice was nearly a tie: {uncertain if uncertain else 'none'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="data/excerpt_manifest.csv")
    a = ap.parse_args()
    m = pd.read_csv(a.manifest).set_index("case_id", drop=False)
    todo = list(m.index)
    failed = []
    for c in todo:
        try:
            annotate(m.loc[c])
        except Exception as e:
            failed.append(c)
            print(f"{c}: FAILED - {type(e).__name__}: {e}")
    print(f"\nDone: {len(todo) - len(failed)} of {len(todo)} annotated" + (f"; failed: {failed}" if failed else ""))
