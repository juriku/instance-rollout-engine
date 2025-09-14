import asyncio
import pytest
from deployment_engine.models import InstanceState, SystemState, DeploymentConfig, Health
from deployment_engine.engine import DeploymentEngine
from deployment_engine.failure import FailureInjector


class TestAdvancedScenarios:
    """Advanced and complex scenario tests."""

    @pytest.mark.asyncio
    async def test_instances_with_different_initial_health_states(self):
        instances = [
            InstanceState("healthy", "oldC", "oldK", Health.HEALTHY),
            InstanceState("degraded", "oldC", "oldK", Health.DEGRADED),
            InstanceState("failed", "oldC", "oldK", Health.FAILED),
        ]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        cfg = DeploymentConfig(batch_size=3)
        engine = DeploymentEngine()

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is True
        # All instances should be updated and healthy after successful deployment
        for instance in instances:
            assert instance.code_version == "newC"
            assert instance.configuration_version == "newK"
            assert instance.health == Health.HEALTHY

    @pytest.mark.asyncio
    async def test_mixed_version_scenarios(self):
        instances = [
            InstanceState("needs_both", "oldC", "oldK"),        # needs both updates
            InstanceState("needs_code", "oldC", "newK"),        # needs code update only
            InstanceState("needs_config", "newC", "oldK"),      # needs config update only
            InstanceState("up_to_date", "newC", "newK"),        # already up to date
        ]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        cfg = DeploymentConfig(batch_size=2)
        engine = DeploymentEngine()

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is True
        assert len(res.updated) == 3  # first three need updates
        assert res.skipped == ["up_to_date"]
        # All should end up at desired state
        for instance in instances:
            assert instance.code_version == "newC"
            assert instance.configuration_version == "newK"

    @pytest.mark.asyncio
    async def test_degraded_instance_during_retries(self):
        instances = [InstanceState("id0", "oldC", "oldK")]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        # Fail once, then succeed
        engine = DeploymentEngine(FailureInjector(fail_attempts={"id0": 1}, delay=0.0))
        cfg = DeploymentConfig(batch_size=1, retry_max_attempts=1, retry_base_delay_s=0.01)

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is True
        assert instances[0].code_version == "newC"
        assert instances[0].health == Health.HEALTHY  # Should be healthy after successful retry

    @pytest.mark.asyncio
    async def test_plan_batches_edge_cases(self):
        # Test batch planning with various instance counts
        instances = [InstanceState(f"id{i}", "oldC", "oldK") for i in range(7)]

        # Test exact division
        batches = DeploymentEngine.plan_batches(instances[:6], 3)
        assert len(batches) == 2
        assert len(batches[0]) == 3
        assert len(batches[1]) == 3

        # Test with remainder
        batches = DeploymentEngine.plan_batches(instances, 3)
        assert len(batches) == 3
        assert len(batches[0]) == 3
        assert len(batches[1]) == 3
        assert len(batches[2]) == 1

        # Test single instance batches
        batches = DeploymentEngine.plan_batches(instances[:3], 1)
        assert len(batches) == 3
        assert all(len(batch) == 1 for batch in batches)

    @pytest.mark.asyncio
    async def test_deployment_result_to_dict(self):
        instances = [InstanceState("id0", "oldC", "oldK")]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        cfg = DeploymentConfig(batch_size=1)
        engine = DeploymentEngine()

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        from dataclasses import asdict
        result_dict = asdict(res)

        assert isinstance(result_dict, dict)
        assert result_dict["success"] is True
        assert result_dict["updated"] == ["id0"]
        assert result_dict["failed"] == []
        assert "history" in result_dict
        assert "per_node_history" in result_dict