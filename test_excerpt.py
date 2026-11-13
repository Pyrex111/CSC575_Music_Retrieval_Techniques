import pretty_midi
from pathlib import Path

# Pick the first excerpt file from your excerpts folder
excerpt_path = Path("data/excerpts/jazz_001.mid")
wav_output_path = Path("jazz_001_preview.wav")

print(f"Synthesizing audio preview for {excerpt_path.name}...")

# Load the excerpt MIDI
pm = pretty_midi.PrettyMIDI(str(excerpt_path))

# Synthesize audio using standard General MIDI soundfonts built into pretty_midi
audio_data = pm.synthesize(fs=44100) # 44.1kHz sample rate

# Save as a .wav file
import scipy.io.wavfile as wavfile
wavfile.write(wav_output_path, 44100, audio_data)

print(f"Audio preview saved to: {wav_output_path.resolve()}")
