"""Create an original 16-bar reference MIDI for renderer validation."""

from pathlib import Path

from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo


def write_reference(path: Path) -> Path:
    beats_per_bar, bars, bpm = 4, 16, 96
    midi = MidiFile(type=1, ticks_per_beat=480)
    tick = midi.ticks_per_beat
    end = bars * beats_per_bar * tick
    conductor = MidiTrack([
        MetaMessage("track_name", name="Abdullah rendering reference"),
        MetaMessage("set_tempo", tempo=bpm2tempo(bpm)),
        MetaMessage("time_signature", numerator=4, denominator=4),
        MetaMessage("end_of_track", time=end),
    ])
    melody = MidiTrack([
        MetaMessage("track_name", name="melody"),
        Message("program_change", channel=0, program=11),
    ])
    accompaniment = MidiTrack([
        MetaMessage("track_name", name="accompaniment"),
        Message("program_change", channel=1, program=32),
        Message("program_change", channel=2, program=24),
    ])
    lead_events, backing_events = [], []

    def note(events, channel, pitch, velocity, start, duration):
        events.append((start, Message("note_on", channel=channel, note=pitch, velocity=velocity)))
        events.append((start + duration, Message("note_off", channel=channel, note=pitch)))

    harmony = ((48, 4), (45, 3), (41, 4), (43, 4))
    for bar in range(bars):
        root, third = harmony[bar % len(harmony)]
        start = bar * beats_per_bar * tick
        for beat, interval in enumerate((7, third, 0, third)):
            length = tick if bar == bars - 1 and beat == 3 else tick * 3 // 4
            note(lead_events, 0, root + 24 + interval, 82, start + beat * tick, length)
        for beat, interval in ((0, 0), (2, 7)):
            note(backing_events, 1, root - 12 + interval, 73, start + beat * tick, tick * 3 // 2)
        for interval in (0, third, 7):
            note(backing_events, 2, root + interval, 58, start + tick // 2, tick * 2)
        for beat in range(beats_per_bar):
            note(backing_events, 9, 36 if beat % 2 == 0 else 38, 62, start + beat * tick, tick // 8)
    for track, events in ((melody, lead_events), (accompaniment, backing_events)):
        last = 0
        for position, message in sorted(events, key=lambda event: (event[0], event[1].type != "note_off")):
            track.append(message.copy(time=position - last))
            last = position
        track.append(MetaMessage("end_of_track", time=end - last))
    midi.tracks.extend([conductor, melody, accompaniment])
    path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(path)
    return path
