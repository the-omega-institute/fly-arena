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


def _child(lab, parent, *, training=None, **changes):
    from flyarena.contracts import FlySpec
    store, service, user, _ = lab
    spec = FlySpec.model_validate(parent['spec'] | {'parent_id': parent['id'], 'name': 'Child'} | changes)
    return store.add_fly(user['id'], spec.model_dump(),
                         service.compiler().compile(spec, publish=True, root=store.root), training=training)


def test_real_multigeneration_links_and_oldest_ancestor_frontier(lab):
    store, _, user, founder = lab
    parent = _child(lab, founder)
    child = _child(lab, parent)
    grandchild = _child(lab, child)
    ledger = LifeLedger(store)
    tree = ledger.lineage(grandchild['id'], user['id'], depth=3)
    assert {(edge['from'], edge['to']) for edge in tree['edges']} == {
        (fly['spec']['parent_id'], fly['id']) for fly in (parent, child, grandchild)}
    tree = ledger.lineage(grandchild['id'], user['id'], depth=2)
    marker = next(n for n in tree['nodes'] if n.get('marker'))
    assert marker['depth'] == -3
    assert {(edge['from'], edge['to']) for edge in tree['edges']} == {
        (parent['id'], child['id']), (child['id'], grandchild['id']), (marker['id'], parent['id'])}


def test_public_child_reuses_private_parent_placeholder_for_private_siblings(lab):
    from test_training import create
    store, _, _, founder = lab
    run = create(lab)
    parent = _child(lab, founder, training=(run['id'], 0, 0))
    child = _child(lab, parent)
    sibling = _child(lab, parent, training=(run['id'], 0, 1))
    ledger = LifeLedger(store)
    assert ledger.visible(child['id']) and not ledger.visible(parent['id']) and not ledger.visible(sibling['id'])
    for depth in (0, 1, 2, 3):
        tree = ledger.lineage(child['id'], depth=depth)
        ancestors = [n for n in tree['nodes'] if n.get('redacted') and n['relation'] == 'ancestor']
        siblings = [n for n in tree['nodes'] if n.get('redacted') and n['relation'] == 'sibling']
        assert len(ancestors) == len(siblings) == 1
        aliases = {ancestors[0]['id']: parent['id'], siblings[0]['id']: sibling['id']}
        actual = {(aliases.get(e['from'], e['from']), aliases.get(e['to'], e['to']))
                  for e in tree['edges'] if not e['from'].startswith('truncated:')}
        expected = {(store.fly(ident)['spec']['parent_id'], ident) for ident in (child['id'], sibling['id'])}
        if depth >= 2:
            expected.add((parent['spec']['parent_id'], parent['id']))
        assert actual == expected
        if depth < 2:
            marker = next(n for n in tree['nodes'] if n.get('marker'))
            assert marker['depth'] == -2
            assert {'from': marker['id'], 'to': ancestors[0]['id'], 'relation': 'ancestor'} in tree['edges']
        serialized = __import__('json').dumps(tree)
        assert parent['id'] not in serialized and sibling['id'] not in serialized


def test_delta_detects_compiler_distinct_model_parameters_and_repeated_edits(lab):
    from flyarena.contracts import FlySpec
    store, service, _, founder = lab
    base = FlySpec.model_validate(founder['spec'])
    mutation = {'selector': 'olfactory', 'scale': 1.01}
    intervention = {'selector': {'pre': {'class': 'A'}}, 'scale': 1.01}
    # Use real pinned annotations rather than an assumed neuron class.
    intervention['selector']['pre'] = {'ids': [str(service.compiler().graph.ids[0])]}
    cases = [
        (base, base.model_copy(update={'model_profile': 'malecns-rate-cpu-v1'})),
        (base, FlySpec.model_validate(base.model_dump() | {'neuron_parameters': {'tau_scale': 1.01}})),
        (base, FlySpec.model_validate(base.model_dump() | {'neuron_parameters': {'threshold_shift_mv': .1}})),
    ]
    for field, item in [('weight_mutations', mutation), ('interventions', intervention)]:
        cases.append(tuple(FlySpec.model_validate(base.model_dump() | {field: [item] * count}) for count in (1, 2)))
    for parent, child in cases:
        before = service.compiler().compile(parent)
        after = service.compiler().compile(child)
        assert before['artifact_id'] != after['artifact_id']
        delta = LifeLedger._design_delta(child.model_dump(), parent.model_dump(), founder['id'])
        assert delta['code'] == 'changed' and delta['changed'] is True
    circuit_delta = LifeLedger._design_delta(cases[3][1].model_dump(), cases[3][0].model_dump())
    assert circuit_delta['circuit_scales'][0]['child'] == 1.01 ** 2
    intervention_delta = LifeLedger._design_delta(cases[4][1].model_dump(), cases[4][0].model_dump())
    assert intervention_delta['intervention_changes']['items'][0]['parent_count'] == 1
    assert intervention_delta['intervention_changes']['items'][0]['child_count'] == 2
    assert LifeLedger._design_delta(base.model_dump(), base.model_dump())['code'] == 'unchanged'


def test_intervention_multiset_ignores_order_but_keeps_multiplicity():
    a = {'selector': {'pre': {'ids': ['1']}}, 'scale': 1.01}
    b = {'selector': {'post': {'ids': ['2']}}, 'scale': 1.02}
    assert LifeLedger._design_delta({'interventions': [a, b, a]}, {'interventions': [b, a, a]})['code'] == 'unchanged'
