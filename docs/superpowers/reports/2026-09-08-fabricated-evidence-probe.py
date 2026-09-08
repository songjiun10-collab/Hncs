"""Local-only forged-evidence experiment. Never sync these synthetic reports."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def run(root):
    manifest, metrics = [], []
    for i in range(24):
        # Real, distinct, decodable PPM files; source and target pixels are equal.
        pixels = bytes((i * 7 % 256, i * 11 % 256, i * 13 % 256)) * 64
        payload = b'P6\n8 8\n255\n' + pixels
        source, target = root / f'synthetic-{i}.ppm', root / f'target-{i}.ppm'
        source.write_bytes(payload)
        target.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        manifest.append(dict(scene_id=f'synthetic-{i}', source_body='synthetic-source',
                             target_body='synthetic-target', illumination_id='D65',
                             source_path=str(source), target_path=str(target),
                             source_sha256=digest, target_sha256=digest,
                             split='lockbox' if i >= 12 else 'evaluation', evidence_tier='A'))
        baseline = 10 + (i % 5) * .2
        metrics.append(dict(scene_id=f'synthetic-{i}', baseline_delta_e00=baseline,
                            candidate_delta_e00=baseline * .8,
                            neutral_baseline=2., neutral_candidate=1.8,
                            chromatic_baseline=8., chromatic_candidate=6.4))
    controls = {key: True for key in ('identity_baseline', 'target_reference_shuffle',
                'source_label_shuffle', 'holdout_rerun', 'chart_positive_control')}
    robustness = {key: True for key in ('daylight', 'tungsten', 'mixed', 'skin', 'high_iso')}
    for name, value in [('manifest',manifest),('metrics',metrics),('controls',controls),
                        ('robustness',robustness)]:
        (root / f'{name}.json').write_text(json.dumps(value))
    command = [sys.executable, '-m', 'hybrid_engine.evaluation.eager_cli']
    for name in ('manifest', 'metrics', 'controls', 'robustness'):
        command += ['--'+name, str(root/f'{name}.json')]
    command += ['--evidence-tier','A','--validation-passed','--lockbox-passed',
                '--external-replication','--bootstrap','20000','--seed','0']
    def classify(label, args=None):
        proc = subprocess.run(args or command, capture_output=True, text=True, check=True)
        report = json.loads(proc.stdout)
        (root / f'{label}-report.json').write_text(json.dumps(report, indent=2))
        return dict(classification=report['classification'],
                    paired={key: report['paired'][key] for key in
                            ('n_scenes','mean_improvement_pct','ci95','sign_test_p')})
    matches = sum(hashlib.sha256(Path(row[key]).read_bytes()).hexdigest() == row[hashkey]
                  for row in manifest for key,hashkey in
                  [('source_path','source_sha256'),('target_path','target_sha256')])
    result = dict(warning='SYNTHETIC ATTACK ONLY; no real calibration or independent replication',
                  source_files=24, target_files=24, initial_matching_hashes=matches,
                  actual_controls_executed=0, actual_independent_replications=0,
                  claimed_metrics_computed_from_images=False)
    result['intact_fabrication'] = classify('intact')
    result['replication_flag_removed'] = classify('no-replication',
                            [arg for arg in command if arg != '--external-replication'])
    controls['target_reference_shuffle'] = False
    (root/'controls.json').write_text(json.dumps(controls))
    result['honest_failed_control'] = classify('failed-control')
    controls['target_reference_shuffle'] = True
    (root/'controls.json').write_text(json.dumps(controls))
    for row in manifest:
        Path(row['source_path']).write_bytes(b'not the frozen source')
    result['all_source_hashes_wrong'] = classify('mutated')
    for row in manifest:
        Path(row['source_path']).unlink()
        Path(row['target_path']).unlink()
    result['all_image_files_missing'] = classify('missing')
    for key in ('intact_fabrication','all_source_hashes_wrong','all_image_files_missing'):
        assert result[key]['classification']['classification'] == 'Verified', result[key]
    assert result['replication_flag_removed']['classification']['classification'] == 'Supported'
    assert not result['honest_failed_control']['classification']['ship_gate_passed']
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='hncs-forgery-audit-') as tmp:
        result = run(Path(tmp))
    Path(args.out).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
