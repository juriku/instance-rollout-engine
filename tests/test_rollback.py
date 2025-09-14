import asyncio
import pytest
from deployment_engine.models import InstanceState, SystemState, DeploymentConfig, Health
from deployment_engine.engine import DeploymentEngine
from deployment_engine.failure import FailureInjector


class TestRollbackScenarios:
    """Rollback functionality tests."""

    @pytest.mark.asyncio
    async def test_rollback_with_partial_batch_completion(self):
        instances = [InstanceState(f"id{i}", "oldC", "oldK") for i in range(6)]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        # First batch succeeds, second batch has failures that trigger rollback
        fail_map = {"id2": 1, "id3": 1}
        cfg = DeploymentConfig(batch_size=2, max_failures=1, retry_max_attempts=0)
        engine = DeploymentEngine(FailureInjector(fail_attempts=fail_map, delay=0.0))

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is False
        assert res.rolled_back is True
        # All instances should be rolled back to original state
        for i in instances:
            assert i.code_version == "oldC"
            assert i.configuration_version == "oldK"

    @pytest.mark.asyncio
    async def test_rollback_restores_health_states(self):
        instances = [
            InstanceState("id0", "oldC", "oldK", Health.HEALTHY),
            InstanceState("id1", "oldC", "oldK", Health.DEGRADED),
            InstanceState("id2", "oldC", "oldK", Health.FAILED),
        ]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        # Fail after first batch to trigger rollback
        fail_map = {"id2": 1}
        cfg = DeploymentConfig(batch_size=2, max_failures=0, retry_max_attempts=0)
        engine = DeploymentEngine(FailureInjector(fail_attempts=fail_map, delay=0.0))

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is False
        assert res.rolled_back is True
        # Health states should be restored
        assert instances[0].health == Health.HEALTHY
        assert instances[1].health == Health.DEGRADED
        assert instances[2].health == Health.FAILED

    @pytest.mark.asyncio
    async def test_rollback_with_already_desired_state_instances(self):
        instances = [
            InstanceState("id0", "oldC", "oldK"),  # needs update
            InstanceState("id1", "newC", "newK"),  # already at desired
            InstanceState("id2", "oldC", "oldK"),  # needs update, will fail
        ]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        fail_map = {"id2": 1}
        cfg = DeploymentConfig(batch_size=2, max_failures=0, retry_max_attempts=0)
        engine = DeploymentEngine(FailureInjector(fail_attempts=fail_map, delay=0.0))

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is False
        assert res.rolled_back is True
        assert res.skipped == ["id1"]
        # All instances should maintain/restore their original state
        assert instances[0].code_version == "oldC"
        assert instances[1].code_version == "newC"  # was already at desired
        assert instances[2].code_version == "oldC"