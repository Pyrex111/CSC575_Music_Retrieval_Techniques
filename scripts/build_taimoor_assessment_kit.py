"""Package audio diagnostics and a reference-guided form for nonexpert listeners."""
import argparse
import csv
import html
import json
from pathlib import Path
import shutil
import zipfile


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--assessment',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args();root=args.checkpoint.resolve();assessment=args.assessment.resolve();dest=args.destination.resolve()
    dest.mkdir(parents=True,exist_ok=True)
    shutil.copytree(root/'listening_kit'/'audio',dest/'audio',dirs_exist_ok=True)
    shutil.copytree(assessment/'external_references',dest/'references',dirs_exist_ok=True)
    hidden=dest/'Read_after_rating';hidden.mkdir(exist_ok=True)
    shutil.copy2(root/'listening_kit'/'DO_NOT_OPEN_UNTIL_RATINGS_COMPLETE'/'method_key.csv',hidden/'method_key.csv')
    for name in ['AUDIO_ASSESSMENT.md','automated_assessments.csv','protocol.json','audio_assessment.json','external_reference_check.json']:
        shutil.copy2(assessment/name,hidden/name)
    shutil.copy2(root/'audio_validation.json',hidden/'audio_validation.json')
    refs=json.loads((assessment/'external_reference_check.json').read_text())['references']
    credits=['# Reference music attribution','',
             'These short reference clips are listening anchors, not training data or generated project outputs. They were not used to select arranger parameters. Each genre contains much more variety than a single example.','']
    for ref in refs:
        credits += [f"## {ref['title']}",'',
                    f"{ref['title']} by Kevin MacLeod (incompetech.com).",
                    'Licensed under Creative Commons Attribution 4.0: https://creativecommons.org/licenses/by/4.0/',
                    'Source: '+ref['source_page'],
                    'Changes: '+ref['changes'],'']
    (dest/'REFERENCE_CREDITS.md').write_text('\n'.join(credits),encoding='utf-8')
    options='<option value="">Choose...</option><option value="jazz">Closer to the Jazz example</option><option value="rock">Closer to the Rock example</option><option value="other">Neither / another style</option><option value="unsure">I cannot judge</option>'
    recognition='<option value="">Choose...</option>'+''.join(f'<option value="{i}">{i} — {label}</option>' for i,label in enumerate(['Cannot recognize it','A little recognizable','Some phrases recognizable','Mostly recognizable','Clearly the same melody'],1))+'<option value="unsure">I cannot judge</option>'
    coherence='<option value="">Choose...</option>'+''.join(f'<option value="{i}">{i} — {label}</option>' for i,label in enumerate(['Mostly jarring','Often awkward','Mixed / acceptable','Mostly natural','Consistently natural'],1))+'<option value="unsure">I cannot judge</option>'
    css='''body{font:17px/1.55 system-ui,sans-serif;background:#f5f7fa;color:#172336;margin:0}main{max-width:1080px;margin:auto;padding:30px 22px 90px}h1{font-size:34px;line-height:1.2}h2{font-size:24px}h3{font-size:19px}.card,section{background:white;border:1px solid #d6dfe9;border-radius:12px;padding:22px;margin:18px 0}.refs{display:grid;grid-template-columns:1fr 1fr;gap:18px}audio{width:100%;max-width:620px}label{display:block;font-weight:600;margin:10px 0 5px}select,input,textarea,button{font:inherit;padding:10px;border:1px solid #a4b2c3;border-radius:6px;box-sizing:border-box}select,textarea{width:100%}textarea{min-height:70px}.questions{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}.version{border-top:1px solid #dfe5ed;padding:20px 0}button{background:#164d85;color:white;cursor:pointer}nav{display:flex;gap:10px;flex-wrap:wrap}.small{font-size:14px;color:#4b5b70}.status{font-weight:600;color:#164d85}.notice{background:#fff6df;border-left:4px solid #d59a18;padding:14px}.sticky{position:sticky;bottom:0;background:#f5f7faee;border-top:1px solid #ccd6e2;padding:15px;display:flex;gap:15px;align-items:center;flex-wrap:wrap}@media(max-width:760px){.refs,.questions{grid-template-columns:1fr}main{padding:20px 12px 80px}section{padding:14px}}'''
    page=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CSC575 guided listening</title><style>'+css+'</style></head><body><main>',
          '<h1>Listen with examples</h1><p>You do not need musical training. Hear the two examples, compare each version with its source, then describe what you hear.</p>',
          '<div class="notice">The automated genre model did not reliably distinguish the project’s development sources. Its diagnostics are included separately. The form below records your own observations; it does not prefill human ratings.</div>',
          '<div class="card"><h2>1. Hear the reference examples</h2><p>These are artist-labelled examples from outside the project. Compare the overall musical style, rather than recording quality. Choose “I cannot judge” whenever needed.</p><div class="refs">',
          '<div><h3>Jazz example — Hot Swing</h3><audio controls preload="none" src="references/jazz_reference.mp3"></audio><p class="small">Kevin MacLeod · 12-second excerpt</p></div>',
          '<div><h3>Rock example — Rock on Chicago</h3><audio controls preload="none" src="references/rock_reference.mp3"></audio><p class="small">Kevin MacLeod · 12-second excerpt</p></div></div><p class="small">Both tracks: Kevin MacLeod (incompetech.com), CC BY 4.0. Excerpts cropped, loudness normalized and faded. <a href="REFERENCE_CREDITS.md">Full attribution and source links</a>.</p></div>',
          '<div class="card"><h2>2. Identify your response</h2><label for="listener">Listener ID or nickname</label><input id="listener" placeholder="For example: listener_01" autocomplete="off"><label for="role">Which describes you?</label><select id="role"><option value="">Choose...</option><option value="internal_developer">Project team member / internal developer</option><option value="external_listener">Listener outside the project team</option></select><p class="small">Start with Excerpts 02 and 05 for a shorter check. A two-excerpt check must be reported as a subset, not a completed eight-excerpt study.</p><nav>'+''.join(f'<a href="#excerpt{i:02}">{i:02}</a>' for i in range(1,9))+'</nav></div>']
    for i in range(1,9):
        excerpt=f'Excerpt_{i:02}'
        page.append(f'<section id="excerpt{i:02}"><h2>3. Excerpt {i:02}</h2><p>Play the source first. Then play A–D with the same volume and headphones or speakers.</p><label>Source</label><audio controls preload="none" src="audio/{excerpt}_source.mp3"></audio>')
        for variant in 'ABCD':
            code=f'{excerpt}_{variant}'
            page.append(f'<div class="version" data-excerpt="{excerpt}" data-version="{variant}"><h3>Version {variant}</h3><audio controls preload="none" src="audio/{code}.mp3"></audio><div class="questions">'
                        f'<div><label for="{code}_genre">Which reference is closer?</label><select id="{code}_genre" data-field="reference_match">{options}</select></div>'
                        f'<div><label for="{code}_melody">Can you recognize the source melody?</label><select id="{code}_melody" data-field="melody_recognizability_1_to_5">{recognition}</select></div>'
                        f'<div><label for="{code}_coherence">Do the notes and transitions fit together?</label><select id="{code}_coherence" data-field="musical_coherence_1_to_5">{coherence}</select></div></div>'
                        f'<label for="{code}_comment">Optional observation — what changed or sounded awkward?</label><textarea id="{code}_comment" data-field="observation" placeholder="For example: the accompaniment changes suddenly near 15 seconds."></textarea></div>')
        page.append('</section>')
    page += ['<div class="card"><h2>4. Save your responses</h2><p>Use the export button when finished. Unrated versions stay blank. The CSV records whether you are a team member, so internal feedback can be reported accurately.</p><p>After saving your responses, you can inspect <a href="Read_after_rating/AUDIO_ASSESSMENT.md">the automated diagnostics</a> and <a href="Read_after_rating/method_key.csv">the method key</a>. Avoid opening these first if you want the versions to remain anonymous.</p></div>',
             '<div class="sticky"><button id="export" type="button">Download my ratings CSV</button><span id="progress" class="status">0 / 32 versions complete</span><span id="message" class="small" role="status"></span></div>',
             r'''<script>
const storageKey='csc575-guided-listening-v1';
const fields=Array.from(document.querySelectorAll('select,input,textarea'));
try {const saved=JSON.parse(localStorage.getItem(storageKey)||'{}');for(const el of fields){if(saved[el.id]!==undefined)el.value=saved[el.id];}}catch(e){}
function update(){let count=0;for(const v of document.querySelectorAll('.version')){if(Array.from(v.querySelectorAll('select')).every(e=>e.value))count++;}document.getElementById('progress').textContent=count+' / 32 versions complete';}
for(const el of fields)el.addEventListener('input',()=>{try{localStorage.setItem(storageKey,JSON.stringify(Object.fromEntries(fields.map(f=>[f.id,f.value]))));}catch(e){}update();});
function escapeCell(value){let s=String(value??'');if(/^[=+@-]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';}
document.getElementById('export').addEventListener('click',()=>{
 const listener=document.getElementById('listener').value.trim(),role=document.getElementById('role').value;
 if(!listener||!role){document.getElementById('message').textContent='Enter a listener ID and choose whether you are a team member first.';return;}
 const header=['listener_id','listener_type','excerpt_id','version','reference_match','melody_recognizability_1_to_5','musical_coherence_1_to_5','observation'];
 const rows=[header];for(const v of document.querySelectorAll('.version')){const values=Object.fromEntries(Array.from(v.querySelectorAll('[data-field]')).map(e=>[e.dataset.field,e.value]));rows.push([listener,role,v.dataset.excerpt,v.dataset.version,values.reference_match,values.melody_recognizability_1_to_5,values.musical_coherence_1_to_5,values.observation]);}
 const csv=rows.map(row=>row.map(escapeCell).join(',')).join('\r\n')+'\r\n';
 const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='CSC575_listener_ratings.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);document.getElementById('message').textContent='CSV downloaded. Keep blank or unsure responses as they are.';
});
update();
</script></main></body></html>''']
    (dest/'index.html').write_text('\n'.join(page),encoding='utf-8')
    (dest/'START_HERE.md').write_text('''# Guided listening and automated audio assessment

Extract this folder and open index.html. No installation or musical training is required.

1. Hear the labelled Jazz and Rock reference clips.
2. Play the source and anonymous A/B/C/D versions for each project excerpt.
3. Choose which reference is closer; rate recognizability and coherence using the plain-language anchors. "I cannot judge" is allowed.
4. Download your responses as CSV. Begin with Excerpts 02 and 05 if you only have time for a subset.

The reference recordings are by Kevin MacLeod, CC BY 4.0. See REFERENCE_CREDITS.md for attribution, source links and changes. They are separate artist-labelled examples, not outputs of the arranger.

Read_after_rating contains completed **machine assessments** for 32 project outputs, model/protocol records and the method key. These are not human ratings. The CLAP model agreed with only 2/4 development-folder labels in a forced Jazz/Rock comparison, so its genre scores are not treated as reliable final ratings. The four original labels also require musical review.

Human recognizability and coherence fields have not been filled automatically. No external listeners, ratings or preferences are invented. Actual team feedback must be described as internal listening.

All project clips retain the previous frozen arrangements. This assessment did not retune the arranger or change the held-out inputs.
''',encoding='utf-8')
    archive=dest.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(dest.rglob('*')):
            if path.is_file():z.write(path,Path(dest.name)/path.relative_to(dest))
    print('Created',archive,'bytes',archive.stat().st_size)


if __name__=='__main__':main()
