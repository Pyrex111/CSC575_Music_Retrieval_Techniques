"""Render a method-anonymized listening kit using Abdullah's pinned renderer."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sys

from workstreams.taimoor.checkpoint import dump, obtain, sha, source_url

RENDER_BLOB='b41aa9eec55532e94e783c09be1963a445afc2e2'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--soundfont',type=Path,required=True)
    parser.add_argument('--fluidsynth',default='fluidsynth')
    args=parser.parse_args();root=args.output.resolve()
    report=json.loads((root/'evaluation_rechecked.json').read_text());plan=json.loads((root/'protocol.json').read_text())
    code=root/'team_code'/'abdullah_render.py'
    obtain(code,source_url(plan,plan['abdullah_revision'],'workstreams/abdullah/render.py'),RENDER_BLOB)
    spec=importlib.util.spec_from_file_location('pinned_abdullah_render',code)
    renderer=importlib.util.module_from_spec(spec);sys.modules[spec.name]=renderer;spec.loader.exec_module(renderer)
    kit=root/'listening_kit';audio=kit/'audio';audio.mkdir(parents=True,exist_ok=True)
    (kit/'DO_NOT_OPEN_UNTIL_RATINGS_COMPLETE').mkdir(exist_ok=True)
    methods=list(plan['methods']);tasks=[];key=[];ratings=[];cases=[]
    randomizer=random.Random(57512)
    for index,case in enumerate(sorted({r['case_id'] for r in report['runs'] if r['split']=='test'}),1):
        label=f'Excerpt_{index:02d}';group=[r for r in report['runs'] if r['case_id']==case]
        tasks.append((label,'source',root/'prepared'/f'{case}.mid'))
        order=randomizer.sample(methods,len(methods))
        for version,method in zip('ABCD',order):
            row=next(r for r in group if r['method']==method)
            tasks.append((label,version,root/row['output']))
            key.append({'excerpt_id':label,'version':version,'case_id':case,'method':method,'target_style':row['target_style']})
            ratings.append({'listener_id':'','excerpt_id':label,'version':version,'heard_genre':'',
                            'melody_recognizability_1_to_5':'','musical_coherence_1_to_5':'','transition_observation':''})
        cases.append(label)
    def render(task):
        label,version,midi=task
        wav=root/'audio_wav'/f'{label}_{version}.wav';mp3=audio/f'{label}_{version}.mp3'
        result=renderer.render_midi(midi,wav,args.soundfont,fluidsynth=args.fluidsynth)
        subprocess.run(['ffmpeg','-hide_banner','-nostdin','-loglevel','error','-y','-i',str(wav),
                        '-codec:a','libmp3lame','-b:a','128k','-map_metadata','-1',str(mp3)],check=True)
        # Verify the deliverable encoding also decodes and has finite loudness/peak.
        lufs,peak=renderer.measure_loudness(mp3,'ffmpeg')
        row=json.loads(json.dumps(asdict(result),default=str))
        row.update({'excerpt_id':label,'version':version,'midi_sha256':sha(midi),'wav_sha256':sha(wav),
                    'mp3':mp3.relative_to(kit).as_posix(),'mp3_sha256':sha(mp3),
                    'mp3_lufs':lufs,'mp3_true_peak_dbtp':peak})
        return row
    rendered=[]
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures=[executor.submit(render,task) for task in tasks]
        for future in as_completed(futures):
            row=future.result();rendered.append(row)
            print(f"Rendered {len(rendered)}/{len(tasks)}: {row['excerpt_id']} {row['version']}",flush=True)
    rendered.sort(key=lambda r:(r['excerpt_id'],r['version']))
    result={'renderer_attribution':'Abdullah, unchanged pinned render.py','renderer_git_blob':RENDER_BLOB,
            'renderer_revision':plan['abdullah_revision'],'soundfont_sha256':sha(args.soundfont),
            'fluidsynth_version':subprocess.run([args.fluidsynth,'-V'],capture_output=True,text=True).stdout,
            'ffmpeg_version':subprocess.run(['ffmpeg','-version'],capture_output=True,text=True).stdout.splitlines()[0],
            'sample_rate_hz':44100,'wav_format':'stereo PCM16','target_lufs':-23,'tail_seconds':0.5,
            'order_seed':57512,'listener_responses_collected':0,'clips':rendered}
    dump(root/'audio_validation.json',result)
    for name,values in [('ratings_blank.csv',ratings),('DO_NOT_OPEN_UNTIL_RATINGS_COMPLETE/method_key.csv',key)]:
        with (kit/name).open('w',newline='',encoding='utf-8') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(values[0]));writer.writeheader();writer.writerows(values)
    intro='''# Listening pilot — no responses collected yet

Open index.html in a browser, or play the MP3 files in the audio folder.
For each excerpt, play the source first, then A/B/C/D in the displayed order.
Use the same device, headphones/speakers, volume and playback settings throughout.

For each version, record these in ratings_blank.csv:
- Heard genre: Jazz, Rock, Other, or Unsure.
- Melody recognizability: 1 (not recognizable) to 5 (clearly recognizable).
- Musical coherence: 1 (very incoherent) to 5 (very coherent).
- A concrete observation about accompaniment or a phrase transition, with time if possible.

Do not open the method key until all ratings are recorded. The target style is
also hidden to reduce prompting. A/B/C/D assignments vary by excerpt.

Eight held-out-for-parameter-selection compositions are provided. If you only
audition a subset, record exactly which ones. Internal developer listening must
be labelled internal, and cannot be reported as an external participant study.
Never fill in other people's ratings or count repeated method files as people.

All clips use Abdullah's pinned FluidSynth rendering procedure, the same
TimGM6mb SoundFont and -23 LUFS target, with a peak ceiling and 0.5-second tail.
MP3 files are listening copies of the validated WAVs; audio_validation.json in
the evaluation evidence records measurements, checksums and the renderer version.
Rendering validates playable audio, not genre quality or musical preference.
'''
    (kit/'README.md').write_text(intro,encoding='utf-8')
    html=['<!doctype html><html><head><meta charset="utf-8"><title>CSC575 listening pilot</title>',
          '<style>body{font:17px system-ui;max-width:850px;margin:40px auto;padding:0 20px;color:#182333}section{border-top:1px solid #ccd5df;padding:16px 0}audio{width:min(100%,550px)}label{display:block;margin:15px 0 4px}p{line-height:1.5}</style></head><body>',
          '<h1>CSC575 listening pilot</h1><p>Play the source, then each version. Record heard genre, melody recognizability (1–5), coherence (1–5), and a concrete transition observation in <a href="ratings_blank.csv">ratings_blank.csv</a>. Keep playback volume unchanged. Read <a href="README.md">the instructions</a> first.</p>',
          '<p>These are source-derived MIDI arrangements with provisional chord and phrase annotations. No listener results are claimed.</p>']
    for label in cases:
        html.append(f'<section><h2>{label.replace("_"," ")}</h2>')
        for version in ['source','A','B','C','D']:
            html.append(f'<label>{version.title()}</label><audio controls preload="none" src="audio/{label}_{version}.mp3"></audio>')
        html.append('</section>')
    html.append('</body></html>');(kit/'index.html').write_text('\n'.join(html),encoding='utf-8')
    print('Listening kit complete; 0 listener responses claimed',flush=True)


if __name__=='__main__':main()
