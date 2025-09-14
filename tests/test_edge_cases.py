import asyncio
import pytest
from deployment_engine.models import InstanceState, SystemState, DeploymentConfig, Health
from deployment_engine.engine import DeploymentEngine
from deployment_engine.failure import FailureInjector


class TestEdgeCasesAndErrorHandling:
    """Edge cases and error handling tests."""

    @pytest.mark.asyncio
    async def test_deploy_empty_instances(self):
        instances = []
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        cfg = DeploymentConfig(batch_size=2)
        engine = DeploymentEngine()

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is True
        assert res.updated == []
        assert res.failed == []
        assert res.skipped == []

    @pytest.mark.asyncio
    async def test_batch_size_larger_than_instances(self):
        instances = [InstanceState(f"id{i}", "oldC", "oldK") for i in range(3)]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        cfg = DeploymentConfig(batch_size=10)
        engine = DeploymentEngine()

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is True
        assert len(res.updated) == 3
        for i in instances:
            assert i.code_version == "newC"
            assert i.configuration_version == "newK"

    def test_invalid_batch_size(self):
        instances = [InstanceState("id0", "oldC", "oldK")]
        with pytest.raises(ValueError, match="batch_size must be > 0"):
            DeploymentEngine.plan_batches(instances, 0)
        with pytest.raises(ValueError, match="batch_size must be > 0"):
            DeploymentEngine.plan_batches(instances, -1)

    @pytest.mark.asyncio
    async def test_timeout_functionality(self):
        instances = [InstanceState("id0", "oldC", "oldK")]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        # Use a very long delay with short timeout
        engine = DeploymentEngine(FailureInjector(fail_attempts={}, delay=1.0))
        cfg = DeploymentConfig(batch_size=1, timeout_s=0.1, retry_max_attempts=0)

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is False
        assert res.failed == ["id0"]
        assert instances[0].health == Health.FAILED

    @pytest.mark.asyncio
    async def test_percentage_failure_threshold(self):
        instances = [InstanceState(f"id{i}", "oldC", "oldK") for i in range(10)]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        # Fail 3 out of 10 (30%), with 25% threshold
        fail_map = {"id1": 1, "id3": 1, "id5": 1}
        cfg = DeploymentConfig(batch_size=2, failure_percentage=25.0, retry_max_attempts=0)
        engine = DeploymentEngine(FailureInjector(fail_attempts=fail_map, delay=0.0))

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is False
        assert res.rolled_back is True
        assert res.aborted_reason == "failure thresholds exceeded"