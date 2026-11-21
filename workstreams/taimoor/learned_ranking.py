"""Adapter between Vinay's pinned model/scoring code and the constrained DP.

The existing heuristic remains the default. Learned scores add a bounded local
penalty; they cannot add candidate notes or override any preservation constraint.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import math
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pretty_midi

from .arranger import PALETTES


VINAY_REVISION = 'dcf7a4218243606e79055212830e08f4bfd9ff55'
VINAY_FILES = {
    'style_features': 'f6c70768cbc5334241dbd1d3f3e9564dfa5a840c',
    'style_classifier': '663b4be857f7f023574bd84cae2cc392e1d73390',
    'style_ranking': 'ac87130a1a541dd5f0c373cfaf744e72adc1b2b5',
}


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_vinay(checkout):
    """Load unchanged teammate functions without leaking bare import aliases."""
    checkout = Path(checkout).resolve()
    revision = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != VINAY_REVISION:
        raise ValueError('Vinay checkout must match pinned revision ' + VINAY_REVISION)
    folder = checkout / 'workstreams/vinay'
    hashes, modules, saved = {}, {}, {name: sys.modules.get(name) for name in VINAY_FILES}
    try:
        for name, expected in VINAY_FILES.items():
            path = folder / (name + '.py')
            data = path.read_bytes()
            actual = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            if actual != expected:
                raise ValueError('Pinned teammate file changed: ' + path.name)
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            modules[name] = module
            hashes[path.name] = file_sha(path)
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return SimpleNamespace(features=modules['style_features'], classifier=modules['style_classifier'],
                           ranking=modules['style_ranking'], hashes=hashes, revision=revision)


def anchored_features(team, midi, melody_index, duration):
    """Use supplied excerpt duration rather than the last sounding note."""
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Descriptor duration must be positive and finite')
    prepared = copy.deepcopy(midi)
    if prepared.get_end_time() > duration + 1e-6:
        raise ValueError('Descriptor input extends beyond its declared duration')
    prepared.text_events.append(pretty_midi.Text('descriptor_duration_anchor', duration))
    features = team.features.extract_style_features(prepared, melody_index)
    names = team.classifier.FEATURE_NAMES
    if set(features) != set(names) or any(not math.isfinite(float(features[k])) for k in names):
        raise ValueError('Invalid or nonfinite teammate feature vector')
    return features


def candidate_midi(song, phrase, candidate, style):
    """Build a phrase-local accompaniment view; melody placeholder is excluded."""
    midi = pretty_midi.PrettyMIDI(initial_tempo=song.tempo)
    midi.time_signature_changes = [pretty_midi.TimeSignature(4, 4, 0)]
    midi.instruments = [pretty_midi.Instrument(73, name='excluded_melody')]
    tracks = {'bass': pretty_midi.Instrument(PALETTES[style][0], name='bass'),
              'chords': pretty_midi.Instrument(PALETTES[style][1], name='chords'),
              'drums': pretty_midi.Instrument(0, is_drum=True, name='drums')}
    for event in candidate.events:
        beat = event.start - phrase.start_bar * 4
        end = beat + event.duration
        limit = phrase.bars * 4
        if beat < -1e-9 or end > limit + 1e-9:
            raise ValueError('Candidate descriptor event is outside the phrase')
        # Removing a large global offset can leave a few ulps at the boundary.
        # Clamp only that descriptor-view roundoff, never an accompaniment event.
        beat, end = max(0.0, beat), min(float(limit), end)
        tracks[event.role].notes.append(pretty_midi.Note(
            event.velocity, event.pitch, beat*song.seconds_per_beat,
            end*song.seconds_per_beat))
    midi.instruments.extend(tracks.values())
    return midi


class LearnedPenalty:
    def __init__(self, team, model, weight, cache=None):
        if not math.isfinite(weight) or weight < 0:
            raise ValueError('Reranker weight must be finite and nonnegative')
        self.team, self.model, self.weight = team, model, weight
        self.cache = {} if cache is None else cache

    def __call__(self, song, phrase, candidate, style):
        # Zero weight must not call a model or alter heuristic choices.
        if self.weight == 0:
            return 0.0
        key = (song.case_id, file_sha(song.annotation_path), phrase.start_bar, candidate.plan, style)
        if key not in self.cache:
            midi = candidate_midi(song, phrase, candidate, style)
            features = anchored_features(self.team, midi, 0, phrase.bars*4*song.seconds_per_beat)
            probability = float(self.team.ranking.calculate_style_score(self.model, features, style))
            if not math.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError('Learned style score must be a probability in [0, 1]')
            self.cache[key] = probability
        return self.weight * phrase.bars * (1-self.cache[key])
