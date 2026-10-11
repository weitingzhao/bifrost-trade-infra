"""TD-304 draft-only route checks, using the existing Alertmanager route walker."""
import copy
import unittest
from pathlib import Path

import yaml
from check_alert_routing import route_to

ROOT = Path(__file__).resolve().parent.parent


class ResearchDeliveryRouteTests(unittest.TestCase):
    def setUp(self):
        self.config = yaml.safe_load((ROOT / 'scripts/k3s/values-kube-prometheus.yaml').read_text())
        self.draft = yaml.safe_load((ROOT / 'docs/audits/TD-304_OWNER_ROUTE_DRAFT.yaml').read_text())
        self.current = self.config['alertmanager']['config']['route']
        self.proposed = copy.deepcopy(self.current)
        self.proposed['routes'][-1:-1] = self.draft['routes']

    def test_two_exact_failure_names_reach_owner_and_audit_only_in_proposal(self):
        for name in ('BifrostDagsterRunFailed', 'BifrostDagsterAssetCheckFailed'):
            labels = {'alertname':name, 'namespace':'research', 'severity':'warning', 'job':'test'}
            self.assertEqual(route_to(self.current, labels), ['bifrost-ops-agent'])
            self.assertEqual(route_to(self.proposed, labels), ['owner-ntfy', 'bifrost-ops-agent'])

    def test_other_warn_namespace_and_similar_names_do_not_get_new_owner_route(self):
        for name, namespace in [('BifrostDagsterRunFailedExtra','research'),
                                ('BifrostDagsterRunFailed','bifrost-dev'),
                                ('BifrostLongCoverageLow','research')]:
            labels = {'alertname':name,'namespace':namespace,'severity':'warning'}
            self.assertEqual(route_to(self.proposed, labels), ['bifrost-ops-agent'])

    def test_existing_watchdog_and_critical_routes_are_preserved(self):
        for labels in ({'alertname':'Watchdog'}, {'alertname':'Other','severity':'critical'}):
            self.assertEqual(route_to(self.current, labels), route_to(self.proposed, labels))

    def test_companion_monitors_require_explicit_addition(self):
        labels = {'alertname':'BifrostResearchMetricsProbeFailing','probe':'alert_delivery'}
        self.assertEqual(route_to(self.proposed, labels), ['bifrost-ops-agent'])
        self.proposed['routes'][-1:-1] = self.draft['companion_routes']
        self.assertEqual(route_to(self.proposed, labels), ['owner-ntfy','bifrost-ops-agent'])
        labels['probe'] = 'schedules'
        self.assertEqual(route_to(self.proposed, labels), ['bifrost-ops-agent'])


if __name__ == '__main__':
    unittest.main()
