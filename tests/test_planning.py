import pytest
from deployment_engine.models import InstanceState
from deployment_engine.engine import DeploymentEngine


def test_plan_respects_batch_size():
    inst = [InstanceState(f"n{i}", "a", "b") for i in range(10)]
    batches = DeploymentEngine.plan_batches(inst, batch_size=3)
    lengths = [len(b) for b in batches]
    assert lengths == [3, 3, 3, 1]
