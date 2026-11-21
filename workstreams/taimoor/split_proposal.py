"""Create a reviewable split proposal without changing the teammate corpus.

Prefer existing unexposed test compositions, then unexposed validation inputs.
All original training compositions and earlier-pilot groups stay out of test.
Duplicate versions are excluded rather than counted as distinct compositions.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
import os
from pathlib import Path

from .team_handoff import assert_revision, composition_key, dump, sha


REVIEW_FIELDS = ('melody_reviewed', 'chords_reviewed', 'phrases_reviewed', 'genre_reviewed',
                 'source_provenance_reviewed', 'composition_grouping_reviewed')


def candidate_splits(records, per_genre_test=10):
    groups = defaultdict(list)
    for row in records:
        groups[row['composition_key']].append(row)
    retained, excluded = [], []
    for key, group in sorted(groups.items()):
        if len({r['source_style'] for r in group}) != 1:
            raise ValueError('Conflicting source genres in composition group: ' + key)
        ordered = sorted(group, key=lambda r: (r['split'] != 'train', r['split'] != 'val', r['case_id']))
        retained.append(ordered[0])
        excluded.extend({'case_id': r['case_id'], 'composition_key': key,
                         'reason': 'Alternate version of retained ' + ordered[0]['case_id']} for r in ordered[1:])
    protected = {r['composition_key'] for r in records if r['split'] == 'train' or r['prior_pilot_matches']}
    test_ids, shortages = set(), {}
    for genre in ('jazz', 'rock'):
        candidates = [r for r in retained if r['source_style'] == genre and r['composition_key'] not in protected]
        candidates.sort(key=lambda r: (r['split'] != 'test', r['case_id']))
        shortages[genre] = max(0, per_genre_test-len(candidates))
        test_ids.update(r['case_id'] for r in candidates[:per_genre_test])
    proposed = []
    for row in sorted(retained, key=lambda r: r['case_id']):
        split = 'test' if row['case_id'] in test_ids else ('train' if row['split'] == 'train' else 'validation')
        proposed.append({**row, 'proposed_split': split})
    return proposed, excluded, shortages, sorted(protected)


def replacement_shortlist(source_root, genre, used):
    path = source_root / f'data/{genre}_dataset.csv'
    if not path.exists():
        return []
    options = []
    for row in csv.DictReader(path.open(encoding='utf-8')):
        try:
            name = row['filename']
            key = composition_key(Path(name).stem)
            tempo = float(row['tempo_bpm'])
            bars = next((b for b in (8,16,24,32) if 30 <= b*240/tempo <= 60), None)
            if key in used or row['status'] != 'Success' or bars is None:
                continue
            if any(row[k].strip().lower() != 'true' for k in ('constant_tempo','only_4_4')):
                continue
            if int(row['pitched_tracks']) < 2 or int(row['drum_tracks']) < 1 or float(row['duration_notes_sec']) < bars*240/tempo:
                continue
            if not (source_root/'data'/genre/name).exists():
                continue
            options.append({'midi_file': name, 'source_style': genre, 'suggested_bars': bars,
                            'tempo_bpm': tempo, 'status': 'Inspection-metadata candidate only; crop/melody/chords/provenance need review'})
        except (ValueError, KeyError, ZeroDivisionError):
            continue
    return sorted(options, key=lambda r: r['midi_file'])[:10]


def propose(handoff, output, source_root=None):
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new empty proposal directory')
    audit_path = handoff/'handoff_audit.json'
    if source_root:
        assert_revision(source_root)
    audit = json.loads(audit_path.read_text())
    if audit['failures']:
        raise ValueError('Resolve individual input failures before proposing splits')
    rows, excluded, shortages, protected = candidate_splits(audit['records'])
    output.mkdir(parents=True, exist_ok=True)
    counts = Counter(r['proposed_split'] for r in rows)
    replacement = []
    for genre in ('jazz', 'rock'):
        validation_count = sum(r['proposed_split'] == 'validation' and r['source_style'] == genre for r in rows)
        if validation_count < 5:
            replacement.append({'source_style': genre, 'split': 'validation', 'compositions_needed': 5-validation_count})
    shortlist = {genre: replacement_shortlist(source_root, genre, {r['composition_key'] for r in rows})
                 for genre in ('jazz','rock')} if source_root else {}
    report = {'status': 'PROPOSAL ONLY; not agreed, reviewed, or used for final evaluation',
              'source_handoff_sha256': sha(audit_path), 'planned_original_cases': audit['planned_compositions'],
              'proposed_unique_compositions': len(rows), 'proposed_split_counts': dict(counts),
              'excluded_alternate_versions': excluded, 'test_shortages': shortages,
              'replacement_requirements': replacement, 'replacement_shortlist': shortlist,
              'replacement_inspection_sha256': {genre:sha(source_root/f'data/{genre}_dataset.csv')
                                                for genre in ('jazz','rock')} if source_root else {},
              'protected_from_test_composition_keys': protected,
              'policy': 'Keep original training groups out of test; exclude earlier pilot groups; prefer unexposed original test cases, then validation; keep one version per normalized composition',
              'changes': [{'case_id': r['case_id'], 'composition': r['composition_id'],
                           'original_split': r['split'], 'proposed_split': r['proposed_split']}
                          for r in rows if ('validation' if r['split']=='val' else r['split']) != r['proposed_split']],
              'rows': rows, 'final_evaluation_ready': False,
              'pending': ['Team agreement on grouped splits and any replacement composition',
                          'Human melody, chord, phrase, genre and provenance reviews',
                          'Document artist/alternate-version limitations; no artist independence is inferred']}
    dump(output/'split_proposal.json', report)
    with (output/'proposed_manifest.csv').open('w', newline='', encoding='utf-8') as handle:
        fields = ['case_id','composition_id','midi_path','genre','split','melody_track_index','original_split']
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n'); writer.writeheader()
        for r in rows:
            writer.writerow({'case_id':r['case_id'], 'composition_id':r['composition_key'],
                             'midi_path':os.path.relpath((handoff/r['midi']).resolve(),output.resolve()),
                             'genre':r['source_style'], 'split':r['proposed_split'],
                             'melody_track_index':r['melody_track'], 'original_split':r['split']})
    with (output/'annotation_review.csv').open('w', newline='', encoding='utf-8') as handle:
        fields = ['case_id','annotation_sha256',*REVIEW_FIELDS,'reviewer','review_note']
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n'); writer.writeheader()
        for r in rows:
            writer.writerow({'case_id':r['case_id'],'annotation_sha256':r['annotation_sha256']})
    print('Proposed split:', dict(counts), '; unique compositions:', len(rows), '; replacements:', replacement)
    return report


def readiness(proposal_dir, reviews_path=None):
    proposal = json.loads((proposal_dir/'split_proposal.json').read_text())
    review_path = reviews_path or proposal_dir/'annotation_review.csv'
    reviews = list(csv.DictReader(review_path.open(encoding='utf-8')))
    by_id = {r['case_id']: r for r in reviews}
    if len(by_id) != len(reviews):
        raise ValueError('Duplicate review rows')
    incomplete = []
    for row in proposal['rows']:
        review = by_id.get(row['case_id'], {})
        approved = all(review.get(k,'').strip().lower() == 'true' for k in REVIEW_FIELDS)
        if (not approved or not review.get('reviewer','').strip() or not review.get('review_note','').strip()
                or review.get('annotation_sha256') != row['annotation_sha256']):
            incomplete.append(row['case_id'])
    rows = proposal['rows']
    counts = Counter(r['proposed_split'] for r in rows)
    groups = defaultdict(set)
    for r in rows:
        groups[r['composition_key']].add(r['proposed_split'])
    tests = [r for r in rows if r['proposed_split']=='test']
    checks = {'sixty_distinct_compositions': len(groups)==60 and len(rows)==60,
              'thirty_ten_twenty_split': counts == {'train':30,'validation':10,'test':20},
              'composition_groups_disjoint': all(len(v)==1 for v in groups.values()),
              'test_excludes_observed_development_groups': all(r['composition_key'] not in proposal['protected_from_test_composition_keys'] for r in tests),
              'reviews_complete_and_hash_bound': not incomplete,
              'team_agreement_recorded': proposal.get('team_agreement_recorded') is True}
    report = {'checks': checks, 'final_evaluation_ready': all(checks.values()),
              'incomplete_review_cases': incomplete, 'proposal_sha256': sha(proposal_dir/'split_proposal.json'),
              'review_sha256': sha(review_path),
              'scope': 'Readiness check only; does not run a model or generate final test outputs'}
    dump(proposal_dir/'readiness.json', report)
    print('Final evaluation ready:', report['final_evaluation_ready'], '; incomplete reviews:', len(incomplete))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('propose','readiness'))
    parser.add_argument('--handoff', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--reviews', type=Path)
    args = parser.parse_args()
    if args.stage=='propose':
        if args.handoff is None:
            parser.error('propose requires --handoff')
        propose(args.handoff.resolve(), args.output.resolve(), args.source_root.resolve() if args.source_root else None)
    else:
        readiness(args.output.resolve(), args.reviews)


if __name__=='__main__':
    main()
