import asyncio
import time
import pytest
from deployment_engine.models import InstanceState, SystemState, DeploymentConfig, Health
from deployment_engine.engine import DeploymentEngine
from deployment_engine.failure import FailureInjector


class TestConcurrencyAndBatching:
    """Concurrency and batching behavior tests."""

    @pytest.mark.asyncio
    async def test_batches_processed_sequentially(self):
        instances = [InstanceState(f"id{i}", "oldC", "oldK") for i in range(6)]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        cfg = DeploymentConfig(batch_size=2)
        engine = DeploymentEngine(FailureInjector(fail_attempts={}, delay=0.1))

        start_time = time.time()
        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        duration = time.time() - start_time

        # Should take at least 0.3 seconds (3 batches * 0.1s delay), but instances within batches run concurrently
        assert duration >= 0.25  # Allow some margin for test timing
        assert res.success is True
        assert len(res.history) >= 6  # batch_start/batch_end for 3 batches

    @pytest.mark.asyncio
    async def test_mixed_success_failure_within_batch(self):
        instances = [InstanceState(f"id{i}", "oldC", "oldK") for i in range(4)]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        # Fail one instance in each batch
        fail_map = {"id0": 1, "id2": 1}
        cfg = DeploymentConfig(batch_size=2, max_failures=5, retry_max_attempts=0)
        engine = DeploymentEngine(FailureInjector(fail_attempts=fail_map, delay=0.0))

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is False
        assert len(res.updated) == 2  # id1 and id3 should succeed
        assert set(res.failed) == {"id0", "id2"}
        assert instances[1].code_version == "newC"  # id1 succeeded
        assert instances[3].code_version == "newC"  # id3 succeeded
        assert instances[0].health == Health.FAILED
        assert instances[2].health == Health.FAILED

    @pytest.mark.asyncio
    async def test_large_instances_small_batches(self):
        instances = [InstanceState(f"id{i}", "oldC", "oldK") for i in range(20)]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        cfg = DeploymentConfig(batch_size=3)
        engine = DeploymentEngine()

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is True
        assert len(res.updated) == 20
        # Should have 7 batches (3+3+3+3+3+3+2)
        batch_events = [h for h in res.history if h["event"] == "batch_start"]
        assert len(batch_events) == 7