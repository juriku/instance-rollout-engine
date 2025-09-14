import asyncio
import time
import pytest
from deployment_engine.models import InstanceState, SystemState, DeploymentConfig, Health
from deployment_engine.engine import DeploymentEngine
from deployment_engine.failure import FailureInjector


class TestConfigurationEdgeCases:
    """Configuration and parameter edge cases tests."""

    @pytest.mark.asyncio
    async def test_both_max_failures_and_percentage_set(self):
        instances = [InstanceState(f"id{i}", "oldC", "oldK") for i in range(10)]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        # Fail 2 instances - this exceeds max_failures but not percentage
        fail_map = {"id1": 1, "id3": 1}
        cfg = DeploymentConfig(batch_size=2, max_failures=1, failure_percentage=50.0, retry_max_attempts=0)
        engine = DeploymentEngine(FailureInjector(fail_attempts=fail_map, delay=0.0))

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is False
        assert res.rolled_back is True
        # Should abort due to max_failures (2 > 1) even though percentage is fine (20% < 50%)

    @pytest.mark.asyncio
    async def test_retry_with_different_backoff_delays(self):
        instances = [InstanceState("id0", "oldC", "oldK")]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        # Fail twice, then succeed
        engine = DeploymentEngine(FailureInjector(fail_attempts={"id0": 2}, delay=0.0))
        cfg = DeploymentConfig(batch_size=1, retry_max_attempts=2, retry_base_delay_s=0.1)

        start_time = time.time()
        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        duration = time.time() - start_time

        assert res.success is True
        # Should have exponential backoff: 0.1s + 0.2s = 0.3s minimum
        assert duration >= 0.25
        assert instances[0].code_version == "newC"
        assert instances[0].health == Health.HEALTHY

    @pytest.mark.asyncio
    async def test_all_instances_already_at_desired_state(self):
        instances = [InstanceState(f"id{i}", "newC", "newK") for i in range(3)]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        cfg = DeploymentConfig(batch_size=2)
        engine = DeploymentEngine()

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is True
        assert res.updated == []
        assert res.skipped == ["id0", "id1", "id2"]
        # Current state should still be updated
        assert current.code_version == "newC"
        assert current.configuration_version == "newK"