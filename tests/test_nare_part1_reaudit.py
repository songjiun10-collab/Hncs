"""Adversarial report-level regression tests for the Part 1 repairs."""
import json
import math
import tempfile
import unittest
from pathlib import Path

from hybrid_engine.evaluation.nare import (
    classify_nare_result, summarize_nare_subgroups,
)
from hybrid_engine.evaluation.nare_cli import build_report
from hybrid_engine.evaluation.eager import classify_result, evaluate_paired, SceneMetric
from hybrid_engine.evaluation.eager_cli import build_report as eager_report


def evidence():
    manifest, metrics = [], []
    for i in range(12):
        manifest.append(dict(scene_id=f's{i}', session_id=f'session{i}', contributor='test',
                             source_path=f'{i}.raw', target_path=f'{i}.jpg',
                             source_sha256=f'{i:064x}', target_sha256=f'{i+100:064x}',
                             picture_style='Provia', split='evaluation',
                             lighting=('daylight','tungsten','mixed')[i%3],
                             scene_type=('portrait','landscape','indoor')[i%3]))
        metrics.append(dict(scene_id=f's{i}', raw_delta_e00=10., foundation_delta_e00=8.,
                            candidate_delta_e00=5., registration=dict(ecc_correlation=.99,
                            overlap_fraction=.99, shift_x_px=1., shift_y_px=0., long_edge_px=512),
                            subgroups={k:dict(baseline_delta_e00=10.,candidate_delta_e00=5.)
                            for k in ('skin','sky','foliage','neutral','saturated','shadow','highlight')}))
    return manifest, metrics


def report(manifest, metrics, controls=None):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        controls = controls if controls is not None else dict(
            subgroups_passed=True, controls_passed=True, provenance_passed=True)
        for name,value in [('manifest',manifest),('metrics',metrics),('controls',controls)]:
            (root / (name+'.json')).write_text(json.dumps(value))
        return build_report(*(str(root/(name+'.json')) for name in ('manifest','metrics','controls')),
                            n_bootstrap=100)


class TestPart1Reaudit(unittest.TestCase):
    def test_direct_paired_evaluation_rejects_negative_optional_errors(self):
        rows = [SceneMetric(f's{i}', 10., 5., neutral_baseline=1., neutral_candidate=-10.)
                for i in range(12)]
        with self.assertRaises(ValueError):
            evaluate_paired(rows, n_bootstrap=100)

    def test_eager_report_cannot_launder_invalid_evidence_into_verified(self):
        for defect in (None, 'numeric_robustness', 'negative_neutral', 'negative_chromatic', 'tier'):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                manifest, metrics = evidence()
                for row in manifest:
                    row.update(source_body='test', target_body='reference', illumination_id='D65',
                               evidence_tier='E' if defect == 'tier' else 'A')
                for row in metrics:
                    row.update(baseline_delta_e00=10., candidate_delta_e00=5.)
                    if defect in ('negative_neutral', 'negative_chromatic'):
                        prefix = defect.replace('negative_', '')
                        row.update({prefix+'_baseline': 1., prefix+'_candidate': -10.})
                controls = {key: True for key in ('identity_baseline', 'target_reference_shuffle',
                            'source_label_shuffle', 'holdout_rerun', 'chart_positive_control')}
                robustness = {'daylight': 0 if defect == 'numeric_robustness' else True}
                root = Path(tmp)
                for name, value in [('manifest',manifest),('metrics',metrics),('controls',controls),
                                    ('robustness',robustness)]:
                    (root/(name+'.json')).write_text(json.dumps(value))
                try:
                    result = eager_report(*(str(root/(name+'.json')) for name in
                                          ('manifest','metrics','controls','robustness')),
                                          'A', True, True, True, n_bootstrap=100)
                except ValueError:
                    if defect is None:
                        raise
                    continue
                classification = result['classification']['classification']
                if defect is None:
                    self.assertEqual(classification, 'Verified')
                else:
                    self.assertNotIn(classification, ('Supported', 'Verified'))

    def assert_blocked(self, manifest, metrics, controls=None):
        try:
            r = report(manifest, metrics, controls)
        except ValueError:
            return
        self.assertFalse(r['classification']['ship_gate_passed'])
        self.assertNotIn(r['classification']['classification'], ('Supported','Verified'))

    def test_valid_report_still_supported(self):
        self.assertTrue(report(*evidence())['classification']['ship_gate_passed'])

    def test_registration_shift_missing_scale_and_false_status_blocked(self):
        for change in ({'shift_x_px':10000}, {'passed':0}, {'passed':'false'},
                       {'failure_reason':'translation'}, {'long_edge_px':None},
                       {'shift_x_px':None}, {'ecc_correlation':True}):
            with self.subTest(change=change):
                m,x = evidence(); x[0]['registration'].update(change)
                self.assert_blocked(m,x)
        m,x=evidence(); del x[0]['registration']['long_edge_px']
        self.assert_blocked(m,x)

    def test_controls_must_be_real_booleans(self):
        for field in ('controls_passed','subgroups_passed','provenance_passed'):
            for value in ('false',1,[False],{'passed':False}):
                with self.subTest(field=field,value=value):
                    controls=dict(controls_passed=True,subgroups_passed=True,provenance_passed=True)
                    controls[field]=value
                    self.assert_blocked(*evidence(),controls)

    def test_duplicate_manifest_cannot_add_fake_coverage(self):
        m,x=evidence()
        for row in m: row.update(lighting='daylight',scene_type='landscape')
        m += [dict(m[0],lighting='tungsten',scene_type='portrait'),
              dict(m[0],lighting='mixed',scene_type='indoor')]
        self.assert_blocked(m,x)

    def test_same_content_cannot_be_relabelled_as_independent_scenes(self):
        for field in ('source_sha256','target_sha256'):
            m,x=evidence()
            for row in m: row[field]=m[0][field]
            with self.subTest(field=field): self.assert_blocked(m,x)

    def test_missing_metadata_cannot_be_stringified_to_valid(self):
        for field in ('scene_id','session_id','contributor','picture_style','source_path'):
            m,x=evidence(); m[0][field]=None
            if field=='scene_id': x[0][field]='None'
            with self.subTest(field=field): self.assert_blocked(m,x)

    def test_coverage_normalizes_case_whitespace_and_unknown(self):
        m,x=evidence()
        for i,row in enumerate(m):
            row.update(lighting=('daylight',' DAYLIGHT ','Daylight')[i%3],
                       scene_type=('portrait',' PORTRAIT ','Portrait')[i%3])
        self.assert_blocked(m,x)
        m,x=evidence()
        for row in m: row['picture_style']='none'
        self.assert_blocked(m,x)

    def test_semantic_finite_overflow_cannot_hide_catastrophic_loss(self):
        m,x=evidence()
        for row in x:
            for group in row['subgroups'].values():
                group.update(baseline_delta_e00=1e308,candidate_delta_e00=1.7e308)
        self.assert_blocked(m,x)

    def test_semantic_underflow_cannot_hide_catastrophic_loss(self):
        m,x=evidence()
        for row in x:
            for group in row['subgroups'].values():
                group.update(baseline_delta_e00=5e-324,candidate_delta_e00=1e-323)
        self.assert_blocked(m,x)

    def test_foundation_aggregate_cannot_publish_nonfinite_supported_report(self):
        m,x=evidence()
        for row in x: row['foundation_delta_e00']=1e308
        try:
            r=report(m,x)
        except ValueError:
            return
        self.assertTrue(math.isfinite(r['paired']['mean_foundation']))
        self.assertTrue(math.isfinite(r['paired']['foundation_improvement_pct']))

    def test_empty_subgroup_contract_and_nan_threshold_rejected(self):
        for kwargs in ({'required':()}, {'catastrophic_regression_pct':float('nan')},
                       {'catastrophic_regression_pct':float('inf')}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                summarize_nare_subgroups([],**kwargs)

    def test_zero_raw_error_has_defined_inconclusive_result(self):
        m,x=evidence()
        for row in x: row.update(raw_delta_e00=0,foundation_delta_e00=0,candidate_delta_e00=0)
        r=report(m,x)
        self.assertFalse(r['classification']['ship_gate_passed'])

    def test_direct_classifiers_reject_malformed_statistics_and_flags(self):
        base=report(*evidence())['paired']
        for change in ({'ci95':[1,-1]}, {'ci95':[1,float('nan')]}, {'ci95':[1]},
                       {'sign_test_p':-1}, {'improvement_pct':float('inf')},
                       {'registration_passed':'false'}, {'n_scenes':12.9}):
            with self.subTest(nare=change):
                try: classified=classify_nare_result(dict(base,**change))
                except ValueError: continue
                self.assertFalse(classified['ship_gate_passed'])
        eager=dict(ci95=[1,2],sign_test_p=.001,mean_improvement_pct=50,
                   controls_passed=True,robustness_passed=True)
        for change in ({'ci95':[1,-1]}, {'ci95':[1,float('nan')]}, {'sign_test_p':-1},
                       {'mean_improvement_pct':float('inf')}, {'controls_passed':'false'}):
            with self.subTest(eager=change):
                classified=classify_result(dict(eager,**change),'A',True,True,True)
                self.assertNotIn(classified['classification'],('Verified','Supported'))
        for field in ('lockbox_passed','validation_passed','external_replication'):
            flags=dict(lockbox_passed=True,validation_passed=True,external_replication=True)
            flags[field]='false'
            with self.subTest(flag=field):
                classified=classify_result(eager,'A',**flags)
                self.assertNotEqual(classified['classification'],'Verified')
