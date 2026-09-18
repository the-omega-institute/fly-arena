import importlib.util
from pathlib import Path
import pytest


def load_script():
    spec=importlib.util.spec_from_file_location('custom_strategy',Path(__file__).parents[1]/'scripts/custom_strategy.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_local_plugin_receives_history_and_config_and_returns_design(tmp_path):
    plugin=tmp_path/'custom.py'
    plugin.write_text('def propose(founder, history, generation, slot, config):\n return dict(founder["spec"], name=config["model"], parent_id=history[0]["fly_id"])\n')
    fn=load_script().load_optimizer(plugin)
    result=fn({'spec':{'name':'WT'}},[{'fly_id':'winner'}],1,1,{'model':'My model'})
    assert result=={'name':'My model','parent_id':'winner'}
    plugin.write_text('propose = None\n')
    with pytest.raises(ValueError,match='must export'):load_script().load_optimizer(plugin)
