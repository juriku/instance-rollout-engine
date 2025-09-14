import asyncio
import pytest
from deployment_engine.models import InstanceState, SystemState, DeploymentConfig, Health
from deployment_engine.engine import DeploymentEngine
from deployment_engine.failure import FailureInjector


class TestBasicDeployment:
    """Basic deployment functionality tests."""

    @pytest.mark.asyncio
    async def test_deploy_all_success(self):
        instances = [InstanceState(f"id{i}", "oldC", "oldK") for i in range(5)]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        cfg = DeploymentConfig(batch_size=2, max_failures=0, retry_max_attempts=0)
        engine = DeploymentEngine(FailureInjector(fail_attempts={}, delay=0.0))

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is True
        assert set(res.updated) == {i.instance_id for i in instances}
        assert res.failed == []
        for i in instances:
            assert i.code_version == "newC"
            assert i.configuration_version == "newK"
            assert i.health == Health.HEALTHY
        assert current.code_version == "newC"
        assert current.configuration_version == "newK"

    @pytest.mark.asyncio
    async def test_abort_and_rollback_on_failures(self):
        instances = [InstanceState(f"id{i}", "oldC", "oldK") for i in range(5)]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        # Make two specific nodes fail on first attempt (no retries)
        fail_map = {"id1": 1, "id3": 1}
        cfg = DeploymentConfig(batch_size=2, max_failures=1, retry_max_attempts=0)
        engine = DeploymentEngine(FailureInjector(fail_attempts=fail_map, delay=0.0))

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is False
        assert res.rolled_back is True
        assert res.aborted_reason == "failure thresholds exceeded"
        # Ensure all nodes are back to original versions
        for i in instances:
            assert i.code_version == "oldC"
            assert i.configuration_version == "oldK"

    @pytest.mark.asyncio
    async def test_dry_run_no_changes(self):
        instances = [InstanceState(f"id{i}", "oldC", "oldK") for i in range(3)]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        cfg = DeploymentConfig(batch_size=2)
        engine = DeploymentEngine()

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg, dry_run=True)
        assert res.success is True
        for i in instances:
            assert i.code_version == "oldC"
            assert i.configuration_version == "oldK"

    @pytest.mark.asyncio
    async def test_retry_backoff_eventually_succeeds(self):
        instances = [InstanceState("id0", "oldC", "oldK")]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK")
        # Fail the first attempt once, then succeed (needs retries >=1)
        engine = DeploymentEngine(FailureInjector(fail_attempts={"id0": 1}, delay=0.0))
        cfg = DeploymentConfig(batch_size=1, retry_max_attempts=1, retry_base_delay_s=0.01)

        res = await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)
        assert res.success is True
        assert res.failed == []
        assert instances[0].code_version == "newC"
        assert instances[0].health == Health.HEALTHY

    @pytest.mark.asyncio
    async def test_deployment_in_progress_with_runtime_error(self):
        instances = [InstanceState("id0", "oldC", "oldK")]
        desired = SystemState("newC", "newK")
        current = SystemState(code_version="oldC", configuration_version="oldK", deployment_in_progress=True)
        engine = DeploymentEngine(FailureInjector(fail_attempts={}, delay=0.0))
        cfg = DeploymentConfig(batch_size=1, max_failures=0, retry_max_attempts=0)
        # Expect RuntimeError due to deployment already in progress
        with pytest.raises(RuntimeError, match="deployment already in progress"):
            await engine.deploy(instances=instances, desired=desired, current=current, config=cfg)