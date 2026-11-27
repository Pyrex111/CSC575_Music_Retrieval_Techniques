
import argparse, datetime, hashlib, json, re, shutil, sys, tempfile
from collections import defaultdict
from pathlib import Path
import pandas as pd

MIDI_EXT = (".mid", ".midi")
LICENCE_TEXT = "Lakh MIDI dataset terms (CC BY 4.0 stated by dataset; individual file authorship unverified)"



def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def version_of(stem):
    m = re.search(r"\.(\d+)$", stem)         
    return int(m.group(1)) if m else 0


def strip_version(stem):
    return re.sub(r"\.\d+$", "", stem)


def clean_title(stem):
    return re.sub(r"\s+", " ", strip_version(stem).replace("_", " ")).strip()


def norm_key(text):
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def save_manifest(df, path):
    shutil.copy2(path, str(path) + ".bak")
    df.to_csv(path, index=False, escapechar="\\")


def refreeze(manifest_path, amendment):
    """Recompute checksum + split counts in manifest_frozen.json and log what was changed."""
    manifest_path = Path(manifest_path)
    df = pd.read_csv(manifest_path)
    fp = manifest_path.with_name("manifest_frozen.json")
    frozen = json.loads(fp.read_text()) if fp.exists() else {}
    frozen.update(n_total=len(df),
                  per_genre_split=df.groupby(["source_style", "split"]).size().to_dict().__repr__(),
                  manifest_sha256=sha256(manifest_path))
    frozen.setdefault("amendments", []).append(f"{datetime.date.today()}: {amendment}")
    fp.write_text(json.dumps(frozen, indent=2))
    print(f"re-froze {fp.name}: {len(df)} rows, sha256 {frozen['manifest_sha256'][:12]}")


def index_midis(root):
    idx = defaultdict(list)
    for p in Path(root).rglob("*"):
        if p.suffix.lower() in MIDI_EXT:
            idx[p.name].append(p)
    return idx



def repair_midi(src, out_dir):
    """Some Lakh files carry a malformed key-signature event that makes mido/pretty_midi refuse the whole file
    even though the notes are fine. Load it tolerantly, drop key-signature events, and save a cleaned copy."""
    import mido
    from mido.midifiles import meta
    cls = meta.MetaSpec_key_signature
    original = cls.decode

    def tolerant(self, message, data):
        try:
            original(self, message, data)
        except Exception:
            message.key = "C"
    cls.decode = tolerant
    try:
        mid = mido.MidiFile(str(src), clip=True)
    finally:
        cls.decode = original
    for t in mid.tracks:
        kept, carry = [], 0
        for m in t:
            if m.type == "key_signature":
                carry += m.time          # keep the timing of everything after it
                continue
            if carry:
                m, carry = m.copy(time=m.time + carry), 0
            kept.append(m)
        t[:] = kept
    out = Path(out_dir) / Path(src).name
    mid.save(str(out))
    return out



def cmd_replace(a):
    import pretty_midi
    from midi_inspector import inspect_midi_file
    from build_manifest import (problems_from_inspection, content_hash, suggest_melody_track,
                                propose_crop, pick_crop_bars)

    man = pd.read_csv(a.manifest).astype(object)   # object dtype so text can go into any column
    old_rows = man[man.case_id == a.remove]
    if len(old_rows) != 1:
        sys.exit(f"{a.remove} not found in {a.manifest}")
    old = old_rows.iloc[0]
    genre = old["source_style"]

    src = Path(a.new_file).resolve()
    root = Path(a.midi_root).resolve()

    info = inspect_midi_file(src)
    repaired = False
    if info["status"] != "Success":
        print(f"  could not parse: {info['status']}")
        try:
            src = repair_midi(src, tempfile.mkdtemp())
            info = inspect_midi_file(src)
            repaired = info["status"] == "Success"
            print("  repaired (removed malformed key-signature events); using a cleaned copy" if repaired
                  else f"  repair did not help: {info['status']}")
        except Exception as e:
            print(f"  repair failed: {type(e).__name__}: {e}")
    reasons = problems_from_inspection(info)
    if reasons:
        sys.exit("new song rejected: " + "; ".join(reasons))
    pm = pretty_midi.PrettyMIDI(str(src))

    
    new_sha, new_content, new_key = sha256(src), content_hash(pm), norm_key(strip_version(src.stem))
    idx = index_midis(root)
    clashes = []
    for _, r in man[man.case_id != a.remove].iterrows():
        if norm_key(strip_version(Path(r["midi_file"]).stem)) == new_key:
            clashes.append((r["case_id"], "same title (ignoring version suffix)"))
        cands = idx.get(r["midi_file"], [])
        if not cands:
            print(f"  note: could not find {r['midi_file']} to hash-compare")
            continue
        if sha256(cands[0]) == new_sha:
            clashes.append((r["case_id"], "identical file"))
        elif content_hash(pretty_midi.PrettyMIDI(str(cands[0]))) == new_content:
            clashes.append((r["case_id"], "identical musical content"))
    if clashes:
        sys.exit(f"new song is a duplicate of existing songs: {clashes}")

 
    print("\npitched tracks in the new song:")
    for i, inst in enumerate(pm.instruments):
        if not inst.is_drum and inst.notes:
            mean_p = sum(n.pitch for n in inst.notes) / len(inst.notes)
            print(f"  [{i}] {inst.name!r:30} program {inst.program:3}  notes {len(inst.notes):4}  mean pitch {mean_p:.0f}")
    mel = a.melody if a.melody is not None else suggest_melody_track(pm)
    if mel is None:
        sys.exit("no melody candidate; pass --melody N")
    print(f"melody track used: {mel} ({'your choice' if a.melody is not None else 'heuristic suggestion - check it'})")

    bpm = info["tempo_bpm"]
    n_bars = pick_crop_bars(bpm)
    start, note = propose_crop(pm, mel, bpm, n_bars)
    if start is None:
        sys.exit(f"cannot crop: {note}")
    bar_s = 240.0 / bpm


    if root not in src.parents:
        dest = root / genre / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        src = dest
        print(f"copied new file to {dest}")

    row = old.to_dict()
    row.update(source_id=src.stem, midi_file=src.name, file_path=src.name, sha256=new_sha,
               title="", artist="", tempo_bpm=bpm, total_bars_in_file=int(info["duration_notes_sec"] // bar_s),
               melody_track=int(mel), melody_track_name=pm.instruments[mel].name,
               melody_program=int(pm.instruments[mel].program), crop_start_bar=int(start),
               crop_bars=int(n_bars), crop_start_sec=round(start * bar_s, 3),
               crop_end_sec=round((start + n_bars) * bar_s, 3))
    man.loc[man.case_id == a.remove, list(row)] = list(row.values())
    save_manifest(man, a.manifest)


    exc_path = Path(a.manifest).with_name("manifest_exclusions.csv")
    exc = pd.read_csv(exc_path) if exc_path.exists() else pd.DataFrame(columns=["genre", "filename", "reason"])
    exc.loc[len(exc)] = dict(genre=genre, filename=old["midi_file"],
                             reason=f"alternate version of another corpus song (removed from {a.remove}); replaced by {src.name}")
    exc.to_csv(exc_path, index=False)

    refreeze(a.manifest, f"{a.remove}: replaced {old['midi_file']} (duplicate version) with {src.name}; split {old['split']} unchanged"
             + ("; source file had malformed key-signature events, cleaned copy used" if repaired else ""))
    print(f"\n{a.remove} is now {src.name}: {n_bars} bars from bar {start + 1}, split={old['split']}, tempo={bpm}")


# ---------- metadata ----------
def cmd_metadata(a):
    man = pd.read_csv(a.manifest)
    idx = index_midis(a.lakh_root)
    lakh_root = Path(a.lakh_root).resolve()

    manual_path = Path(a.manual)
    manual = {}
    if manual_path.exists():
        for _, r in pd.read_csv(manual_path, dtype=str).fillna("").iterrows():
            if r["artist"].strip() and r["title"].strip():
                manual[r["case_id"]] = (r["artist"].strip(), r["title"].strip())

    found, todo = {}, []
    for _, r in man.iterrows():
        cands = idx.get(r["midi_file"], [])
        if len(cands) > 1:   # same filename under several artists: use the hash to pick the right one
            cands = [c for c in cands if sha256(c) == str(r["sha256"])] or []
        if len(cands) == 1 and cands[0].parent.resolve() != lakh_root:
            found[r["case_id"]] = (cands[0].parent.name, clean_title(Path(r["midi_file"]).stem))
        else:
            todo.append(r)
    found.update(manual)   
    todo = [r for r in todo if r["case_id"] not in manual]

    man["artist"] = [found.get(c, ("", ""))[0] or "" for c in man.case_id]
    man["title"] = [found.get(c, ("", ""))[1] or "" for c in man.case_id]
    man["version"] = [version_of(Path(f).stem) for f in man.midi_file]
    man["work_key"] = [norm_key(f"{ar} {ti}") if ar and ti else norm_key(strip_version(Path(f).stem))
                       for ar, ti, f in zip(man.artist, man.title, man.midi_file)]
    save_manifest(man, a.manifest)
    print(f"artist/title filled for {len(found)} of {len(man)} songs")

    if todo:
        pd.DataFrame([dict(case_id=r["case_id"], midi_file=r["midi_file"], artist="", title=clean_title(Path(r["midi_file"]).stem))
                      for r in todo]).to_csv(manual_path, index=False)
        print(f"{len(todo)} songs could not be matched -> fill artist/title in {manual_path} and re-run this command")

    
    for key, g in man.groupby("work_key"):
        if len(g) > 1:
            cross = " <-- CROSSES SPLITS" if g.split.nunique() > 1 else ""
            print(f"DUPLICATE WORK: {list(g.case_id)} splits={list(g.split)}{cross}")

    # propagate to excerpt manifest + annotation JSONs
    meta = man.set_index("case_id")[["artist", "title", "version", "work_key"]]
    if Path(a.excerpt_manifest).exists():
        ex = pd.read_csv(a.excerpt_manifest)
        for col in meta.columns:
            ex[col] = ex.case_id.map(meta[col])
        ex.to_csv(a.excerpt_manifest, index=False, escapechar="\\")
        print(f"updated {a.excerpt_manifest}")
    n = 0
    for c, r in meta.iterrows():
        jp = Path(a.excerpt_dir) / f"{c}.json"
        if not jp.exists():
            continue
        d = json.loads(jp.read_text())
        prov = d["provenance"]
        prov = re.sub(r"title: [^;]*;", lambda m: f"title: {(r['title'] or 'TODO').replace(';', ',')};", prov)
        prov = re.sub(r"artist: [^;]*;", lambda m: f"artist: {(r['artist'] or 'TODO').replace(';', ',')};", prov)
        prov = prov.replace("licence: TODO", f"licence: {LICENCE_TEXT}")
        if prov != d["provenance"]:
            d["provenance"] = prov
            jp.write_text(json.dumps(d, indent=2))
            n += 1
    print(f"patched provenance in {n} annotation JSONs (chords/phrases untouched)")
    refreeze(a.manifest, f"filled artist/title/version/work_key for {len(found)} songs")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("replace", "metadata"):
        p = sub.add_parser(name)
        p.add_argument("--manifest", default="data/dataset_manifest.csv")
        if name == "replace":
            p.add_argument("--remove", required=True, help="case_id to replace, e.g. jazz_020")
            p.add_argument("--new_file", required=True)
            p.add_argument("--midi_root", default="data")
            p.add_argument("--melody", type=int, default=None, help="melody track index (default: heuristic)")
        else:
            p.add_argument("--lakh_root", required=True, help="the ORIGINAL clean_midi folder (Artist/Title.mid)")
            p.add_argument("--manual", default="metadata_manual.csv")
            p.add_argument("--excerpt_manifest", default="data/excerpt_manifest.csv")
            p.add_argument("--excerpt_dir", default="data/excerpts")
    a = ap.parse_args()
    cmd_replace(a) if a.cmd == "replace" else cmd_metadata(a)
