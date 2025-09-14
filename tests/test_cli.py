import json
import tempfile
import os
import pytest
from unittest.mock import patch
from deployment_engine.cli import load_instances, save_instances
from deployment_engine.models import InstanceState, Health


class TestCLIFileOperations:
    """Test CLI file loading and saving operations with real files."""

    def test_load_instances_valid_json(self):
        """Test loading instances from valid JSON file."""
        test_data = [
            {"instance_id": "id1", "code_version": "v1", "configuration_version": "c1", "health": "healthy"},
            {"instance_id": "id2", "code_version": "v1", "configuration_version": "c1", "health": "degraded"}
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        try:
            instances = load_instances(temp_path)
            assert len(instances) == 2
            assert instances[0].instance_id == "id1"
            assert instances[0].health == Health.HEALTHY
            assert instances[1].health == Health.DEGRADED
        finally:
            os.unlink(temp_path)

    def test_load_instances_missing_health_defaults_to_healthy(self):
        """Test loading instances with missing health field defaults to healthy."""
        test_data = [
            {"instance_id": "id1", "code_version": "v1", "configuration_version": "c1"}
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        try:
            instances = load_instances(temp_path)
            assert len(instances) == 1
            assert instances[0].health == Health.HEALTHY
        finally:
            os.unlink(temp_path)

    def test_save_and_load_instances_roundtrip(self):
        """Test saving and loading instances maintains data integrity."""
        instances = [
            InstanceState("id1", "v1", "c1", Health.HEALTHY),
            InstanceState("id2", "v1", "c1", Health.FAILED)
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name

        try:
            # Save instances
            save_instances(temp_path, instances)

            # Load them back
            loaded_instances = load_instances(temp_path)

            # Verify data integrity
            assert len(loaded_instances) == 2
            assert loaded_instances[0].instance_id == "id1"
            assert loaded_instances[0].health == Health.HEALTHY
            assert loaded_instances[1].instance_id == "id2"
            assert loaded_instances[1].health == Health.FAILED
        finally:
            os.unlink(temp_path)

    def test_load_instances_file_not_found(self):
        """Test loading instances from non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_instances("non_existent_file.json")

    def test_load_instances_invalid_json(self):
        """Test loading instances from invalid JSON raises JSONDecodeError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            temp_path = f.name

        try:
            with pytest.raises(json.JSONDecodeError):
                load_instances(temp_path)
        finally:
            os.unlink(temp_path)

    def test_load_instances_with_all_health_states(self):
        """Test loading instances with all possible health states."""
        test_data = [
            {"instance_id": "healthy", "code_version": "v1", "configuration_version": "c1", "health": "healthy"},
            {"instance_id": "degraded", "code_version": "v1", "configuration_version": "c1", "health": "degraded"},
            {"instance_id": "failed", "code_version": "v1", "configuration_version": "c1", "health": "failed"}
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        try:
            instances = load_instances(temp_path)
            assert len(instances) == 3
            assert instances[0].health == Health.HEALTHY
            assert instances[1].health == Health.DEGRADED
            assert instances[2].health == Health.FAILED
        finally:
            os.unlink(temp_path)


class TestCLIArgumentParsing:
    """Test CLI argument parsing without executing commands."""

    def test_help_displays_correctly(self):
        """Test that help command exits cleanly."""
        with patch('sys.argv', ['deployment-engine', '--help']):
            with pytest.raises(SystemExit) as exc_info:
                from deployment_engine.cli import main
                main()
            assert exc_info.value.code == 0

    def test_deploy_help_displays_correctly(self):
        """Test that deploy help command exits cleanly."""
        with patch('sys.argv', ['deployment-engine', 'deploy', '--help']):
            with pytest.raises(SystemExit) as exc_info:
                from deployment_engine.cli import main
                main()
            assert exc_info.value.code == 0

    def test_rollback_help_displays_correctly(self):
        """Test that rollback help command exits cleanly."""
        with patch('sys.argv', ['deployment-engine', 'rollback', '--help']):
            with pytest.raises(SystemExit) as exc_info:
                from deployment_engine.cli import main
                main()
            assert exc_info.value.code == 0

    def test_missing_command_fails(self):
        """Test CLI fails when no command is provided."""
        with patch('sys.argv', ['deployment-engine']):
            with pytest.raises(SystemExit) as exc_info:
                from deployment_engine.cli import main
                main()
            assert exc_info.value.code != 0

    def test_missing_required_arguments_fails(self):
        """Test CLI fails when required arguments are missing."""
        # Missing both instances and desired
        with patch('sys.argv', ['deployment-engine', 'deploy']):
            with pytest.raises(SystemExit) as exc_info:
                from deployment_engine.cli import main
                main()
            assert exc_info.value.code != 0

        # Missing desired argument
        with patch('sys.argv', ['deployment-engine', 'deploy', '--instances', 'instances.json']):
            with pytest.raises(SystemExit) as exc_info:
                from deployment_engine.cli import main
                main()
            assert exc_info.value.code != 0

        # Missing snapshot argument for rollback
        with patch('sys.argv', ['deployment-engine', 'rollback']):
            with pytest.raises(SystemExit) as exc_info:
                from deployment_engine.cli import main
                main()
            assert exc_info.value.code != 0

    def test_invalid_argument_values_fail(self):
        """Test CLI fails with invalid argument values."""
        # Invalid log level
        with patch('sys.argv', ['deployment-engine', '--log-level', 'INVALID', 'deploy', '--instances', 'i.json', '--desired', 'd.json']):
            with pytest.raises(SystemExit) as exc_info:
                from deployment_engine.cli import main
                main()
            assert exc_info.value.code != 0

        # Invalid batch size (non-integer)
        with patch('sys.argv', ['deployment-engine', 'deploy', '--instances', 'i.json', '--desired', 'd.json', '--batch-size', 'invalid']):
            with pytest.raises(SystemExit) as exc_info:
                from deployment_engine.cli import main
                main()
            assert exc_info.value.code != 0

        # Invalid max-failures (non-integer)
        with patch('sys.argv', ['deployment-engine', 'deploy', '--instances', 'i.json', '--desired', 'd.json', '--max-failures', 'invalid']):
            with pytest.raises(SystemExit) as exc_info:
                from deployment_engine.cli import main
                main()
            assert exc_info.value.code != 0


class TestCLIIntegration:
    """Integration tests for CLI with real example files."""

    def test_cli_with_example_files_dry_run(self):
        """Test CLI works with actual example files in dry-run mode."""
        # This test uses the actual example files that should exist
        example_instances = "examples/instances.json"
        example_desired = "examples/desired.json"

        # Only run if example files exist
        if os.path.exists(example_instances) and os.path.exists(example_desired):
            with patch('sys.argv', [
                'deployment-engine', 'deploy',
                '--instances', example_instances,
                '--desired', example_desired,
                '--dry-run'
            ]):
                # Should not raise any exceptions for dry run
                from deployment_engine.cli import main
                main()
        else:
            pytest.skip("Example files not found")

    def test_load_actual_example_instances(self):
        """Test loading the actual example instances file."""
        example_instances = "examples/instances.json"

        if os.path.exists(example_instances):
            instances = load_instances(example_instances)
            assert len(instances) > 0
            assert all(isinstance(inst, InstanceState) for inst in instances)
            assert all(inst.instance_id for inst in instances)  # All have IDs
        else:
            pytest.skip("Example instances file not found")