"""Exact FIX2 report-boundary regression; authored reports, no scientific calls."""
import unittest
import mechanics_source_tests as s
from mechanics_fix1_tests import reports
from flyarena.experiments.contact_mechanics_v1.verify import checked_report,panel_admission

class PrimaryPhaseReportContracts(unittest.TestCase):
    def trial(self,profile):
        return next(t for t in s.panel('development') if t.profile==profile and t.seed==42 and t.case[0]=='straight-008')

    def test_zero_invalid_phase_full_panel_still_passes(self):
        values=reports()
        self.assertTrue(all(r['primary']['invalid_interior_phase_episodes']==0 for r in values.values()))
        self.assertTrue(panel_admission(values,'development')['passed'])

    def test_candidate_positive_phase_count_with_both_gates_passing_rejects(self):
        values=reports();trial=self.trial(s.PROFILE)
        values[trial.identity]['primary']['invalid_interior_phase_episodes']=1
        with self.assertRaisesRegex(ValueError,'invalid primary phase episodes'):
            panel_admission(values,'development')

    def test_comparator_positive_phase_count_with_both_gates_passing_rejects(self):
        values=reports();trial=self.trial(s.CONTROL)
        values[trial.identity]['primary']['invalid_interior_phase_episodes']=1
        with self.assertRaisesRegex(ValueError,'invalid primary phase episodes'):
            panel_admission(values,'development')

    def coherent_failure(self,profile,gate):
        values=reports();trial=self.trial(profile);value=values[trial.identity]
        value['primary']['invalid_interior_phase_episodes']=1
        value['primary'][gate+'_passed']=False;value['gates'][gate]=False
        value['all_original_gates_pass']=False;value['candidate_passed']=False
        self.assertFalse(checked_report(trial,value))
        return values

    def test_candidate_with_either_original_gate_failed_remains_honest_failure(self):
        for gate in ('recovery','support_slip'):
            with self.subTest(gate=gate):
                values=self.coherent_failure(s.PROFILE,gate)
                self.assertFalse(panel_admission(values,'development')['passed'])

    def test_comparator_with_either_original_gate_failed_does_not_veto_candidate(self):
        for gate in ('recovery','support_slip'):
            with self.subTest(gate=gate):
                values=self.coherent_failure(s.CONTROL,gate)
                self.assertTrue(panel_admission(values,'development')['passed'])
