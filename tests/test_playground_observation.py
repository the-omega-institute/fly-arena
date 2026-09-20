from types import SimpleNamespace
import numpy as np
from flyarena.observation import display_indices, population_summary, MORPHOLOGY_IDS, MORPHOLOGY_CONNECTOME


def test_recording_covers_all_visible_ids_without_geometry_or_duplicates():
    ids=np.array(sorted(MORPHOLOGY_IDS+[999999999]))
    graph=SimpleNamespace(ids=ids,manifest={'sha256':MORPHOLOGY_CONNECTOME})
    selected=display_indices(graph,[0,0,len(ids)-1])
    assert len(selected)==233
    assert set(ids[selected])==set(ids)
    graph.manifest['sha256']='other'
    assert display_indices(graph,[1,2,1])==[1,2]


def test_full_network_summary_includes_zero_and_high_rates():
    result=population_summary([0,1,2,401])
    assert result['neuron_count']==4 and result['active_count']==2
    assert result['above_400hz_count']==1 and result['mean_hz']==101
