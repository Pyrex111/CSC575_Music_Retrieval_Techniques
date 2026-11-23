"""Streamlit interface for Objective 2 PI1 and PI2."""

from pathlib import Path
import os
import shutil

import streamlit as st

from workstreams.abdullah.demo_backend import (
    MidiInputError,
    RendererSettings,
    load_midi,
    render_playback,
    validate_pair,
)
from workstreams.abdullah.render import RenderError


def main() -> None:
    st.set_page_config(page_title="Cross-Genre Song Transformer", page_icon="🎵", layout="centered")
    st.title("Cross-Genre Song Transformer")

    with st.sidebar:
        st.header("Audio rendering")
        soundfont = st.text_input(
            "SoundFont file", value=os.environ.get("CSC575_SOUNDFONT", "/usr/share/sounds/sf2/TimGM6mb.sf2"),
        )
        with st.expander("Renderer paths"):
            fluidsynth = st.text_input("FluidSynth", value=os.environ.get("CSC575_FLUIDSYNTH", "fluidsynth"))
            ffmpeg = st.text_input("FFmpeg", value=os.environ.get("CSC575_FFMPEG", "ffmpeg"))
        st.caption("44.1 kHz stereo WAV · Same SoundFont and loudness procedure for both previews")

    uploaded_source = st.file_uploader("Source MIDI", type=["mid", "midi"], key="source_upload")
    if uploaded_source is None:
        st.session_state.pop("playback", None)
        st.info("Load a constant-tempo, 4/4 MIDI excerpt to choose its melody track and target style.")
        return
    try:
        source = load_midi(uploaded_source.getvalue(), uploaded_source.name)
    except MidiInputError as exc:
        st.session_state.pop("playback", None)
        st.error(str(exc))
        return

    st.caption(f"{source.filename} · {source.duration_seconds:.2f} s · {source.tempo_bpm:.2f} BPM · 4/4")
    melody_column, style_column = st.columns(2)
    with melody_column:
        melody_track = st.selectbox(
            "Melody track", source.melody_indices,
            format_func=lambda index: source.tracks[index].label,
            key=f"melody_{source.sha256}",
            help="Indices match the arrangement backend's PrettyMIDI instrument list. Drum and empty tracks are excluded.",
        )
    with style_column:
        style_label = st.selectbox("Target style", ("Jazz", "Rock"), key="target_style")
    target_style = style_label.lower()
    with st.expander("MIDI tracks"):
        st.dataframe([
            {"Index": track.index, "Name": track.name or "Unnamed", "Program": track.program,
             "Drums": track.is_drum, "Notes": track.note_count}
            for track in source.tracks
        ], hide_index=True, width="stretch")

    context = source.sha256, melody_track, target_style
    uploaded_transformed = st.file_uploader(
        "Prepared transformed MIDI", type=["mid", "midi"],
        key=f"transformed_{source.sha256}_{melody_track}_{target_style}",
        help="Load an exported arrangement for this source, melody selection, and target style.",
    )
    st.caption("Use the arrangement backend's exported MIDI for the selected melody and target style.")
    transformed = None
    valid_pair = True
    if uploaded_transformed is not None:
        try:
            transformed = load_midi(uploaded_transformed.getvalue(), uploaded_transformed.name)
            validate_pair(source, transformed)
        except MidiInputError as exc:
            st.session_state.pop("playback", None)
            st.error(str(exc))
            transformed = None
            valid_pair = False

    settings = RendererSettings(Path(soundfont), fluidsynth, ffmpeg)
    try:
        settings_identity = settings.identity()
    except OSError:
        settings_identity = soundfont, None, fluidsynth, ffmpeg
    playback_key = context, transformed.sha256 if transformed else None, settings_identity
    saved = st.session_state.get("playback")
    if saved is not None and saved["key"] != playback_key:
        st.session_state.pop("playback", None)
    ready = (
        bool(soundfont.strip()) and settings_identity[1] is not None
        and shutil.which(fluidsynth) is not None and shutil.which(ffmpeg) is not None
    )
    if not ready:
        st.warning("Set an existing SoundFont file and available renderer paths in Audio rendering to prepare playback.")
    if st.button("Prepare playback", type="primary", disabled=not ready or not valid_pair):
        st.session_state.pop("playback", None)
        try:
            with st.spinner("Preparing WAV audio…"):
                assets = render_playback(
                    source, transformed, melody_track=melody_track,
                    target_style=target_style, settings=settings,
                )
            st.session_state["playback"] = {"key": playback_key, "assets": assets}
        except (RenderError, OSError, MidiInputError) as exc:
            st.error(f"Playback could not be prepared. {exc}")

    saved = st.session_state.get("playback")
    assets = saved["assets"] if saved is not None else None
    if assets is not None and assets.peak_limited_outputs:
        st.warning("A preview is below the target loudness because it reached the peak limit.")
    source_column, transformed_column = st.columns(2)
    with source_column:
        st.subheader("Source")
        if assets is not None:
            st.audio(assets.source_wav, format="audio/wav", alt="Original MIDI rendered as audio")
        st.download_button(
            "Download source MIDI", source.data, file_name=source.filename,
            mime="audio/midi", on_click="ignore", width="stretch",
        )
        st.download_button(
            "Download source WAV", assets.source_wav if assets else b"",
            file_name=f"{Path(source.filename).stem}_source.wav", mime="audio/wav",
            disabled=assets is None, on_click="ignore", width="stretch",
        )
    with transformed_column:
        st.subheader("Transformed")
        if assets is not None and assets.transformed_wav is not None:
            st.audio(assets.transformed_wav, format="audio/wav", alt="Prepared transformed MIDI rendered as audio")
        if transformed is None and valid_pair:
            st.caption("Load a prepared transformed MIDI to enable its playback and downloads.")
        st.download_button(
            "Download transformed MIDI", transformed.data if transformed else b"",
            file_name=transformed.filename if transformed else "transformed.mid", mime="audio/midi",
            disabled=transformed is None, on_click="ignore", width="stretch",
        )
        st.download_button(
            "Download transformed WAV", assets.transformed_wav if assets and assets.transformed_wav else b"",
            file_name=f"{Path(source.filename).stem}_{target_style}.wav", mime="audio/wav",
            disabled=assets is None or assets.transformed_wav is None,
            on_click="ignore", width="stretch",
        )


if __name__ == "__main__":
    main()
