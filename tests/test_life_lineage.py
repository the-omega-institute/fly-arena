"""Bounded lineage is derived from immutable FlySpec and recorded evidence."""
from test_life_ledger import finish
from test_training import lab
from flyarena.services.life import LifeLedger


def test_lineage_depth_order_and_explicit_frontier_marker(lab):
    store, service, user, parent = lab
    run = finish(lab)
    child = parent['id']
    tree = LifeLedger(store).lineage(child, user['id'], depth=0)
    assert tree['center_id'] == child
    assert tree['nodes'][0]['id'] == child
    assert all(node.get('depth', 0) <= 1 for node in tree['nodes'] if not node.get('marker'))
    assert any(node.get('marker') and node['direction'] == 'descendants' for node in tree['nodes'])
    assert all(edge['from'] in {node['id'] for node in tree['nodes']} and edge['to'] in {node['id'] for node in tree['nodes']} for edge in tree['edges'])


def test_lineage_delta_is_relative_to_parent_and_keeps_recorded_evidence(lab):
    store, service, user, parent = lab
    run = finish(lab)
    child = run['members'][-1]['fly_id']
    node = next(node for node in LifeLedger(store).lineage(child, user['id'], depth=2)['nodes'] if node['id'] == child)
    assert node['delta']['relative_to_parent'] == parent['id'] or node['delta']['relative_to_parent'] == run['members'][-2]['fly_id']
    assert isinstance(node['delta']['changed_circuits'], list)
    assert node['evaluation_results']
    assert all(item['match_id'] in node['replay_links'][0] for item in node['evaluation_results'][:1])


def test_lineage_redacts_private_siblings_for_public_viewer(lab):
    store, service, user, parent = lab
    run = finish(lab)
    tree = LifeLedger(store).lineage(parent['id'], None, depth=1)
    private = [node for node in tree['nodes'] if node.get('redacted')]
    assert private
    assert all(node['label'] == 'Private design' for node in private)
    assert all('owner' not in node and node.get('parent_id') is None for node in private)


def test_lineage_delta_codes_distinguish_founder_unchanged_and_changed():
    parent = {'weight_mutations': [], 'neuron_parameters': {'tau_scale': 1, 'threshold_shift_mv': 0}}
    assert LifeLedger._design_delta(parent, None)['code'] == 'founder'
    unchanged = LifeLedger._design_delta(parent, parent, 'parent')
    assert unchanged['code'] == 'unchanged' and unchanged['changed'] is False
    child = parent | {'neuron_parameters': {'tau_scale': 1.2, 'threshold_shift_mv': 0}}
    changed = LifeLedger._design_delta(child, parent, 'parent')
    assert changed['code'] == 'changed' and changed['changed'] is True
    assert changed['changed_parameters'][0]['parent'] == 1
    assert changed['changed_parameters'][0]['child'] == 1.2
    assert changed['relative_to_parent'] == 'parent'


def test_lineage_restricted_parent_has_unavailable_code_not_unchanged(lab, monkeypatch):
    store, service, user, parent = lab
    run = finish(lab)
    child = run['members'][-1]['fly_id']
    ledger = LifeLedger(store)
    visible = ledger.visible
    monkeypatch.setattr(ledger, 'visible', lambda ident, owner=None: ident != parent['id'] and visible(ident, owner))
    node = next(node for node in ledger.lineage(child, user['id'])['nodes'] if node['id'] == child)
    assert node['delta']['code'] == 'parent_unavailable'
    assert node['delta']['changed'] is None
    assert node['delta']['edge_changes']['count'] is None
    assert node['delta']['relative_to_parent'] is None
