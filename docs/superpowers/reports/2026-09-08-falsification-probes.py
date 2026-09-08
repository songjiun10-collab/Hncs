"""Read-only counterexamples: run from repository root with PYTHONPATH=."""
import copy
import json
from hybrid_engine.evaluation.nare import evaluate_nare_metrics, classify_nare_result, summarize_nare_subgroups

GROUPS = ('skin', 'sky', 'foliage', 'neutral', 'saturated', 'shadow', 'highlight')
manifest = [dict(scene_id=str(i), session_id=str(i), contributor='synthetic',
    source_path=f'{i}.raw', target_path=f'{i}.jpg', source_sha256=f'{i:064x}',
    target_sha256=f'{i+100:064x}', picture_style='Provia', lighting=str(i%3),
    scene_type=str(i%3), split='evaluation') for i in range(12)]
metrics = [dict(scene_id=str(i), raw_delta_e00=10, foundation_delta_e00=10,
    candidate_delta_e00=5, registration=dict(ecc_correlation=.99, overlap_fraction=1),
    subgroups={k:dict(baseline_delta_e00=10,candidate_delta_e00=5) for k in GROUPS}) for i in range(12)]

def evaluate(m, x):
    r = evaluate_nare_metrics(m, x, n_bootstrap=100)
    r.update(subgroups_passed=True, controls_passed=True, provenance_passed=True)
    return r, classify_nare_result(r)

output = {}
bad = copy.deepcopy(metrics)
for x in bad:
    x['registration'] = dict(ecc_correlation=-1, overlap_fraction=0)
output['invalid_registration'] = evaluate(manifest,bad)[1]
bad_manifest = copy.deepcopy(manifest)
for x in bad_manifest:
    x['lighting'] = 'daylight'
    x['scene_type'] = 'landscape'
for i in range(2):
    x = dict(manifest[i],scene_id=f'train-{i}',split='discovery',lighting=f'train-light-{i}',scene_type=f'train-type-{i}')
    bad_manifest.append(x)
output['training_coverage_leak'] = evaluate(bad_manifest,metrics)[1]
extra = dict(metrics[0], candidate_delta_e00=100)
try:
    evaluate(manifest, metrics + [extra])
except ValueError as error:
    output['duplicate_order'] = {'rejected': str(error)}
for value in (float('nan'), 100):
    x = dict(subgroups={k:dict(baseline_delta_e00=0,candidate_delta_e00=value) for k in GROUPS})
    try:
        output[f'subgroup_zero_{value}'] = summarize_nare_subgroups([x])
    except ValueError as error:
        output[f'subgroup_zero_{value}'] = {'rejected': str(error)}
from unittest.mock import patch
from tools.fuji import fit_nare_provia_session_holdout as fitter
lockbox = [dict(scene_id='same-scene',session_id=str(i),split='lockbox') for i in range(3)]
with patch.object(fitter, '_load_frame', side_effect=lambda row, dim: row), patch.object(fitter, '_score', return_value=10):
    try:
        fitter.fit(lockbox)
    except ValueError as error:
        output['fit_rejects_lockbox_and_duplicate_scene'] = str(error)
import importlib
import numpy as np
from pathlib import Path
from gui.tabs.brand_preview import list_shipped_looks
failures = []
count = 0
images = [np.zeros((32,32,3),np.uint8), np.full((32,32,3),255,np.uint8),
          np.random.default_rng(0).integers(0,256,(32,32,3),dtype=np.uint8)]
for module, name in list_shipped_looks():
    function = getattr(importlib.import_module(module),name)
    for image in images:
        try:
            rendered = function(image.copy())
            assert rendered.shape in ((32,32),(32,32,3))
            assert rendered.dtype == np.uint8 and np.isfinite(rendered).all()
            count += 1
        except Exception as error:
            failures.append([module,name,str(error)])
output['render_contract'] = dict(passed=count,failures=failures)
artifact = json.loads(Path('datasets/fuji/contributed/dpreview-gfx100rf-preprod-2026-08/nare_provia_session_holdout_fit_512px_2026-09.json').read_text())
output['nonzero_fit_sessions'] = sorted({r['held_out_session'] for r in artifact['per_scene'] if r['improvement'] != 0})
docs = [p for p in Path('docs').rglob('*.md') if not p.name.endswith('.en.md') and p.name not in ('AGENTS.md','CLAUDE.md')]
output['missing_english_filename_pairs'] = sorted(str(p) for p in docs if not p.with_name(p.stem+'.en.md').exists())
print(json.dumps(output,indent=2))
