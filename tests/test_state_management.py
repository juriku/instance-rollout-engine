import asyncio
import pytest
from deployment_engine.models import InstanceState, SystemState, DeploymentConfig, Health
from deployment_engine.engine import DeploymentEngine
from deployment_engine.failure import FailureInjector


class TestStateManagement:
    """State management and tracking tests."""

    @pytest.mark.asyncio
    async def test_deployment_in_progress_flag_management(self):
        instances = [InstanceState("id0", "oldC", "oldK")]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        cfg = DeploymentConfig(batch_size=1)
        engine = DeploymentEngine()

        assert current.deployment_in_progress is False
        await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        # Flag should be reset after deployment
        assert current.deployment_in_progress is False

    @pytest.mark.asyncio
    async def test_deployment_in_progress_flag_reset_on_failure(self):
        instances = [InstanceState("id0", "oldC", "oldK")]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        fail_map = {"id0": 1}
        cfg = DeploymentConfig(batch_size=1, max_failures=0, retry_max_attempts=0)
        engine = DeploymentEngine(FailureInjector(fail_attempts=fail_map, delay=0.0))

        assert current.deployment_in_progress is False
        await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        # Flag should be reset even after failed deployment
        assert current.deployment_in_progress is False

    @pytest.mark.asyncio
    async def test_current_state_not_updated_on_failure(self):
        instances = [InstanceState("id0", "oldC", "oldK")]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        fail_map = {"id0": 1}
        cfg = DeploymentConfig(batch_size=1, max_failures=0, retry_max_attempts=0)
        engine = DeploymentEngine(FailureInjector(fail_attempts=fail_map, delay=0.0))

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is False
        # Current state should remain unchanged
        assert current.code_version == "oldC"
        assert current.configuration_version == "oldK"

    @pytest.mark.asyncio
    async def test_history_tracking_complex_scenario(self):
        instances = [InstanceState(f"id{i}", "oldC", "oldK") for i in range(5)]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        # Fail in second batch to trigger rollback
        fail_map = {"id2": 1}
        cfg = DeploymentConfig(batch_size=2, max_failures=0, retry_max_attempts=0)
        engine = DeploymentEngine(FailureInjector(fail_attempts=fail_map, delay=0.0))

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)

        # Check global history
        assert len(res.history) >= 4  # batch_start, batch_end, batch_start, abort
        abort_events = [h for h in res.history if h["event"] == "abort"]
        assert len(abort_events) == 1
        assert abort_events[0]["reason"] == "failure thresholds exceeded"

        # Check per-node history
        assert "id0" in res.per_node_history
        assert "id1" in res.per_node_history
        assert "id2" in res.per_node_history
        assert res.per_node_history["id2"][0]["event"] == "failed"