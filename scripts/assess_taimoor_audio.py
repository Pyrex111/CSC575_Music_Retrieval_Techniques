"""Independent local CLAP audio assessment; never fabricates human ratings.

Requires onnxruntime and transformers==4.57.1 for its NumPy audio utilities and
tokenizer. ONNX encoders run locally; no project audio is sent to a service.
The unfused NumPy log-mel path follows Hugging Face's Apache-2.0 CLAP extractor.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import subprocess
import time
from urllib.request import urlopen

import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer
from transformers.audio_utils import mel_filter_bank, spectrogram, window_function


REPO='Xenova/clap-htsat-unfused'
REVISION='c28f2883575e590e04d3146ff0713c2448d691ba'
FILES=['config.json','preprocessor_config.json','tokenizer.json','tokenizer_config.json',
       'special_tokens_map.json','vocab.json','merges.txt',
       'onnx/audio_model_quantized.onnx','onnx/text_model_quantized.onnx']
GENRES=['jazz','rock','classical','pop','blues','country','reggae','electronic','hip hop','folk']
TEMPLATES=['This audio is a {genre} song.','The sound of {genre} music.',
           'An instrumental {genre} music recording.']


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def normalize(a):
    return a/np.maximum(np.linalg.norm(a,axis=-1,keepdims=True),1e-12)


def download_models(cache):
    manifest=[]
    for name in FILES:
        path=cache/name;path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            with urlopen(f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}?download=true',timeout=90) as response,path.open('wb') as handle:
                while block:=response.read(1024*1024):handle.write(block)
        manifest.append({'file':name,'bytes':path.stat().st_size,'sha256':sha(path)})
    return manifest


class AudioJudge:
    def __init__(self,cache):
        options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
        self.audio=ort.InferenceSession(str(cache/'onnx/audio_model_quantized.onnx'),options,providers=['CPUExecutionProvider'])
        self.text=ort.InferenceSession(str(cache/'onnx/text_model_quantized.onnx'),options,providers=['CPUExecutionProvider'])
        self.tokenizer=AutoTokenizer.from_pretrained(str(cache),local_files_only=True)
        self.config=json.loads((cache/'preprocessor_config.json').read_text())
        c=self.config
        self.mels=mel_filter_bank(513,64,c['frequency_min'],c['frequency_max'],48000,norm='slaney',mel_scale='slaney')
        self.window=window_function(1024,'hann')
        prompts=[template.format(genre=genre) for genre in GENRES for template in TEMPLATES]
        # Process each text separately: this ONNX text export has input_ids only,
        # so padding multiple unequal texts would have no attention mask.
        texts=[]
        for prompt in prompts:
            ids=self.tokenizer(prompt,return_tensors='np')['input_ids'].astype(np.int64)
            texts.append(normalize(self.text.run(None,{'input_ids':ids})[0])[0])
        self.prompt_embeddings=np.array(texts).reshape(len(GENRES),len(TEMPLATES),-1)
        self.genre_embeddings=normalize(self.prompt_embeddings.mean(axis=1))

    def feature(self,audio):
        if len(audio)!=480000:raise ValueError('Audio model accepts exact 10-second windows at 48 kHz')
        mel=spectrogram(audio,self.window,frame_length=1024,hop_length=480,power=2.0,
                        mel_filters=self.mels,log_mel='dB').T
        return mel.astype(np.float32)[None,None,:,:]

    def assess(self,path,music_duration):
        result=subprocess.run(['ffmpeg','-hide_banner','-nostdin','-loglevel','error','-i',str(path),
                               '-t',str(music_duration),'-ac','1','-ar','48000','-f','f32le','pipe:1'],
                              check=True,capture_output=True)
        samples=np.frombuffer(result.stdout,dtype='<f4').copy()
        if not np.isfinite(samples).all() or np.max(np.abs(samples))==0:
            raise ValueError('Nonfinite or silent audio cannot be genre-assessed')
        if len(samples)<480000:raise ValueError('Clip shorter than 10 seconds')
        n=max(1,math.ceil(music_duration/10))
        starts=np.linspace(0,len(samples)-480000,n).round().astype(int)
        segments=[];embeddings=[]
        for start in starts:
            features=self.feature(samples[start:start+480000])
            embedding=normalize(self.audio.run(None,{'input_features':features})[0])[0]
            scores=embedding@self.genre_embeddings.T
            prompt_scores=np.einsum('d,gtd->gt',embedding,self.prompt_embeddings)
            segments.append({'start_seconds':int(start)/48000,'duration_seconds':10,
                             'top_genre':GENRES[int(np.argmax(scores))],
                             'genre_cosines':dict(zip(GENRES,map(float,scores))),
                             'prompt_template_genre_cosines':prompt_scores.tolist()})
            embeddings.append(embedding)
        mean_embedding=normalize(np.mean(embeddings,axis=0)[None,:])[0]
        clip_scores=np.mean([[s['genre_cosines'][g] for g in GENRES] for s in segments],axis=0)
        ranking=np.argsort(clip_scores)[::-1]
        winner=GENRES[int(ranking[0])]
        return {'genre_cosines':dict(zip(GENRES,map(float,clip_scores))),
                'top_genre':winner,'top_two_margin':float(clip_scores[ranking[0]]-clip_scores[ranking[1]]),
                'jazz_vs_rock_choice':'jazz' if clip_scores[0]>clip_scores[1] else 'rock',
                'jazz_minus_rock_cosine':float(clip_scores[0]-clip_scores[1]),
                'segment_top_choice_agreement':sum(s['top_genre']==winner for s in segments)/len(segments),
                'audio_embedding':mean_embedding.tolist(),'segments':segments}


def summarize(output,report):
    rows=report['clips'];outputs=[r for r in rows if r['role']=='output'];controls=[r for r in rows if r['role']=='reference_control']
    lines=['# Audio-based assessment — automated, not human listening','',
           'The frozen arranger was not modified or retuned. This is a post hoc, independently pretrained audio-model check of the rendered WAV files.',
           'CLAP similarities are not calibrated probabilities or validated 1–5 listening scores. Human coherence and recognizability ratings remain unfilled.','',
           '## Source/reference checks','',
           '| Development source | Folder label | Top of 10 genre prompts | Jazz/Rock choice | Jazz minus Rock cosine |',
           '| --- | --- | --- | --- | ---: |']
    for r in controls:lines.append(f"| {r['case_id']} | {r['source_style']} | {r['top_genre']} | {r['jazz_vs_rock_choice']} | {r['jazz_minus_rock_cosine']:.4f} |")
    correct=sum(r['jazz_vs_rock_choice']==r['source_style'] for r in controls)
    lines += ['',f'Agreement with the four development-folder labels: **{correct}/4** for the forced Jazz/Rock choice. This very small check is not a validated accuracy estimate; folders themselves are not independently re-labelled.','',
              '## Held-out output summaries','',
              '| Method | Top-of-10 matches target | Jazz/Rock choice matches target | Mean target-minus-opposite cosine | Mean source-to-output target-margin change |',
              '| --- | ---: | ---: | ---: | ---: |']
    for method in ['instrument_only','fixed','adaptive','no_continuity']:
        group=[r for r in outputs if r['method']==method]
        lines.append(f"| {method} | {sum(r['top_genre']==r['target_style'] for r in group)}/8 | {sum(r['jazz_vs_rock_choice']==r['target_style'] for r in group)}/8 | {np.mean([r['target_minus_opposite_cosine'] for r in group]):.4f} | {np.mean([r['target_margin_change_from_source'] for r in group]):.4f} |")
    lines += ['', '## Per-output machine assessments','',
              '| Excerpt | Version | Model top genre | Jazz/Rock choice | Target-minus-opposite cosine | Melody events | Human coherence |',
              '| --- | --- | --- | --- | ---: | --- | --- |']
    for r in outputs:
        lines.append(f"| {r['excerpt_id']} | {r['version']} | {r['top_genre']} | {r['jazz_vs_rock_choice']} | {r['target_minus_opposite_cosine']:.4f} | pass | not collected |")
    lines += ['', '## Interpretation limits','',
              '- The model receives decoded waveforms only. It is separate from the arranger, its local scoring function and Vinay\'s symbolic descriptor proxy.',
              '- Prompts, model revision and deterministic windows were fixed before project-audio inference. No prompt selection based on favourable outputs was performed.',
              '- It is a quantized ONNX conversion of a general audio-text model. Its behaviour on General MIDI SoundFont synthesis is not independently validated.',
              '- A forced two-genre choice always chooses Jazz or Rock, even when neither fits. Read it alongside the top-of-10 genre and raw margins.',
              '- A similarity increase supports only model-based style evidence. It does not establish musical coherence, original-song recognizability or human preference.',
              '- No listener identities, ratings, consent records or human observations have been generated.',
              '- Prompt-template and segment-level scores are retained to expose instability. Small-sample counts should remain exploratory.','',
              'Model: https://huggingface.co/Xenova/clap-htsat-unfused ; original: https://huggingface.co/laion/clap-htsat-unfused .',
              'Method: Wu et al., Large-scale Contrastive Language-Audio Pretraining with Feature Fusion and Keyword-to-Caption Augmentation, ICASSP 2023 (arXiv:2211.06687).','']
    (output/'AUDIO_ASSESSMENT.md').write_text('\n'.join(lines),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.checkpoint.resolve();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    if (output/'audio_assessment.json').exists():raise ValueError('Assessment already exists; retain rather than silently overwrite.')
    model_files=download_models(args.cache)
    key=list(csv.DictReader((root/'listening_kit'/'DO_NOT_OPEN_UNTIL_RATINGS_COMPLETE'/'method_key.csv').open()))
    lookup={(k['excerpt_id'],k['version']):k for k in key}
    audio=json.loads((root/'audio_validation.json').read_text())
    evaluations=json.loads((root/'evaluation_rechecked.json').read_text())
    prep=json.loads((root/'preparation.json').read_text())
    protocol={'model_repo':REPO,'model_revision':REVISION,'model_files':model_files,
              'genres':GENRES,'prompt_templates':TEMPLATES,
              'window_rule':'Full-coverage, evenly spaced overlapping 10-second windows; ceil(music-duration/10) windows. Exclude 0.5-second release tail.',
              'score_rule':'Mean per-window cosine to normalized three-prompt genre mean; no softmax or 1-5 conversion.',
              'input_audio_report_sha256':sha(root/'audio_validation.json'),
              'arranger_selection_sha256':sha(root/'frozen_selection.json'),
              'no_arranger_retuning':True,'human_ratings_collected':0,'code_sha256':sha(__file__)}
    write_json(output/'protocol.json',protocol)
    judge=AudioJudge(args.cache)
    tasks=[]
    for record in prep['prepared']:
        if record['split']=='development':
            path=root/'reference_wav'/f"{record['case_id']}.wav"
            if not path.exists():raise ValueError('Render development-reference WAVs before assessment')
            tasks.append({'path':path,'music_duration':record['duration_seconds'],'role':'reference_control',
                          'case_id':record['case_id'],'source_style':record['source_style']})
    for clip in audio['clips']:
        excerpt,variant=clip['excerpt_id'],clip['version']
        if variant=='source':
            entry=next(k for k in key if k['excerpt_id']==excerpt)
            source=next(r for r in evaluations['runs'] if r['case_id']==entry['case_id'])
            metadata={'role':'source','case_id':entry['case_id'],'source_style':source['source_style'],
                      'target_style':entry['target_style'],'excerpt_id':excerpt,'version':variant}
        else:
            entry=lookup[(excerpt,variant)]
            metadata={'role':'output',**entry}
        tasks.append({'path':root/'audio_wav'/f'{excerpt}_{variant}.wav','music_duration':clip['midi_duration_seconds'],**metadata})
    rows=[];cache={};started=time.perf_counter()
    for index,item in enumerate(tasks,1):
        path=item.pop('path');duration=item.pop('music_duration');digest=sha(path)
        if digest not in cache:cache[digest]=judge.assess(path,duration)
        row={**item,'audio_sha256':digest,'music_duration_seconds':duration,**cache[digest]}
        rows.append(row)
        print(f"Assessed {index}/{len(tasks)}: {item.get('case_id')} {item.get('version','reference')} -> {row['top_genre']}",flush=True)
        write_json(output/'partial_results.json',{'clips':rows,'planned_clips':len(tasks)})
    sources={r['case_id']:r for r in rows if r['role']=='source'}
    for r in rows:
        if r['role']!='output':continue
        target=r['target_style'];opposite='rock' if target=='jazz' else 'jazz'
        r['target_minus_opposite_cosine']=r['genre_cosines'][target]-r['genre_cosines'][opposite]
        source=sources[r['case_id']]
        source_margin=source['genre_cosines'][target]-source['genre_cosines'][opposite]
        r['target_margin_change_from_source']=r['target_minus_opposite_cosine']-source_margin
        r['source_audio_embedding_similarity']=float(np.array(r['audio_embedding'])@np.array(source['audio_embedding']))
        r['human_recognizability_1_to_5']=None;r['human_coherence_1_to_5']=None
    report={'assessment_type':'automated_CLAP_waveform_assessment','protocol':protocol,
            'runtime':{'python':platform.python_version(),'onnxruntime':version('onnxruntime'),
                       'transformers':version('transformers'),'elapsed_seconds':time.perf_counter()-started},
            'human_ratings_collected':0,'clips':rows}
    write_json(output/'audio_assessment.json',report)
    fields=['excerpt_id','version','case_id','method','target_style','top_genre','jazz_vs_rock_choice',
            'target_minus_opposite_cosine','target_margin_change_from_source','segment_top_choice_agreement',
            'source_audio_embedding_similarity','human_recognizability_1_to_5','human_coherence_1_to_5']
    with (output/'automated_assessments.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for r in rows:
            if r['role']=='output':writer.writerow({k:r.get(k) for k in fields})
    summarize(output,report)
    print('Completed machine assessments; human rating fields intentionally unfilled.',flush=True)


if __name__=='__main__':main()
