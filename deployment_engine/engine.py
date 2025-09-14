import asyncio
from .models import Health, DeploymentResult
from .failure import FailureInjector
from .logger import get_logger


class DeploymentEngine:
    def __init__(self, failure_injector=None):
        self.failure_injector = failure_injector if failure_injector else FailureInjector()
        self.logger = get_logger("engine")

    @staticmethod
    def plan_batches(instances, batch_size):
        """Split instances into batches for deployment"""
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")

        # Convert to list if needed and create batches
        instance_list = list(instances)
        batches = []
        for i in range(0, len(instance_list), batch_size):
            batch = instance_list[i:i + batch_size]
            batches.append(batch)
        return batches

    async def _update_instance(self, instance, desired, config):
        """Update a single instance with retries and timeout handling"""

        # Apply timeout if configured
        if config.timeout_s and config.timeout_s > 0:
            try:
                return await asyncio.wait_for(self._do_update(instance, desired, config), timeout=config.timeout_s)
            except asyncio.TimeoutError:
                instance.health = Health.FAILED
                self.logger.error(f"Update timed out for instance {instance.instance_id} after {config.timeout_s}s")
                return False, "timeout"
        else:
            return await self._do_update(instance, desired, config)

    async def _do_update(self, instance, desired, config):
        """The actual update logic with retries"""
        max_attempts = max(1, config.retry_max_attempts + 1)  # +1 because we count initial attempt

        for attempt in range(1, max_attempts + 1):
            try:
                # Add some delay to simulate real deployment work
                delay = self.failure_injector.delay_seconds()
                if delay > 0:
                    await asyncio.sleep(delay)

                # Check if we should simulate a failure
                if self.failure_injector.should_fail(instance):
                    raise Exception("Simulated deployment failure")

                # Actually update the instance
                instance.code_version = desired.code_version
                instance.configuration_version = desired.configuration_version
                instance.health = Health.HEALTHY
                self.logger.info(f"Successfully updated instance {instance.instance_id}")
                return True, None

            except Exception as e:
                self.logger.warning(f"Update attempt {attempt} failed for {instance.instance_id}: {str(e)}")

                if attempt >= max_attempts:
                    # Final attempt failed
                    instance.health = Health.FAILED
                    self.logger.error(f"Instance {instance.instance_id} failed after {attempt} attempts")
                    return False, str(e)
                else:
                    # Mark as degraded while retrying
                    instance.health = Health.DEGRADED

                    # Simple exponential backoff
                    backoff_time = min((2 ** (attempt - 1)) * config.retry_base_delay_s, 30.0)
                    self.logger.info(f"Retrying in {backoff_time} seconds...")
                    await asyncio.sleep(backoff_time)

        return False, "Max attempts exceeded"

    async def rollback(self, instances, snapshot):
        """Rollback instances to previous state using snapshot"""
        self.logger.warning(f"Starting rollback for {len(instances)} instances")

        # Restore each instance from snapshot
        for instance in instances:
            if instance.instance_id in snapshot:
                snap = snapshot[instance.instance_id]
                instance.code_version = snap["code_version"]
                instance.configuration_version = snap["configuration_version"]
                instance.health = Health(snap["health"])
                self.logger.debug(f"Rolled back instance {instance.instance_id}")
            else:
                self.logger.warning(f"No snapshot found for instance {instance.instance_id}")

        self.logger.info("Rollback completed")

    def _process_batch_results(self, batch, outcomes, batch_idx, result, updated, failed):
        """Process the results from a batch deployment"""
        batch_updated = 0
        batch_failed = 0

        for instance, (success, error) in zip(batch, outcomes):
            # Track per-instance history
            if instance.instance_id not in result.per_node_history:
                result.per_node_history[instance.instance_id] = []

            if success:
                updated.append(instance.instance_id)
                batch_updated += 1
                result.per_node_history[instance.instance_id].append({
                    "event": "updated",
                    "batch": batch_idx
                })
            else:
                failed.append(instance.instance_id)
                batch_failed += 1
                result.per_node_history[instance.instance_id].append({
                    "event": "failed",
                    "batch": batch_idx,
                    "error": error
                })

        self.logger.info(f"Batch {batch_idx} completed: {batch_updated} updated, {batch_failed} failed")

    def _check_failure_limits(self, total_instances, failed_count, config):
        """Check if we've exceeded failure thresholds"""
        if total_instances == 0 or failed_count == 0:
            return False

        # Check absolute failure limit
        if config.max_failures is not None and failed_count > config.max_failures:
            self.logger.warning(f"Exceeded max failures: {failed_count} > {config.max_failures}")
            return True

        # Check percentage failure limit
        if config.failure_percentage is not None:
            failure_rate = (failed_count / total_instances) * 100.0
            if failure_rate > config.failure_percentage:
                self.logger.warning(f"Exceeded failure percentage: {failure_rate:.1f}% > {config.failure_percentage}%")
                return True

        return False

    def _find_instances_to_update(self, instances, desired):
        """Find which instances need updates"""
        to_update = []
        already_updated = []

        for instance in instances:
            needs_code_update = instance.code_version != desired.code_version
            needs_config_update = instance.configuration_version != desired.configuration_version

            if needs_code_update or needs_config_update:
                to_update.append(instance)
                self.logger.debug(f"Instance {instance.instance_id} needs update")
            else:
                already_updated.append(instance.instance_id)

        self.logger.info(f"Found {len(to_update)} instances to update, {len(already_updated)} already up to date")
        return to_update, already_updated

    def _handle_dry_run_or_no_updates(self, result, instances_to_update, dry_run, desired, current):
        """Handle dry run mode or when no updates are needed"""
        result.success = True

        if dry_run:
            self.logger.info(f"DRY RUN: Would update {len(instances_to_update)} instances")
            result.history.append({"event": "dry_run", "instances_planned": len(instances_to_update)})
        else:
            if len(instances_to_update) == 0:
                self.logger.info("All instances already up to date")
                result.history.append({"event": "no_updates_needed", "count": 0})
                # Update system state since everything is current
                current.code_version = desired.code_version
                current.configuration_version = desired.configuration_version

    async def _run_batches(self, batches, desired, config, result, instances, snapshot):
        """Run deployment batches one by one"""
        updated = []
        failed = []

        for batch_idx, batch in enumerate(batches, start=1):
            self.logger.info(f"Starting batch {batch_idx}/{len(batches)} with {len(batch)} instances")
            result.history.append({"event": "batch_start", "batch": batch_idx, "nodes": [i.instance_id for i in batch]})

            # Update all instances in this batch at the same time
            update_tasks = []
            for instance in batch:
                task = self._update_instance(instance, desired, config)
                update_tasks.append(task)

            # Wait for all updates in this batch to complete
            batch_results = await asyncio.gather(*update_tasks)
            self._process_batch_results(batch, batch_results, batch_idx, result, updated, failed)

            # Check if we should abort due to too many failures
            total_instances = sum(len(b) for b in batches)
            if self._check_failure_limits(total_instances, len(failed), config):
                result.aborted_reason = "failure thresholds exceeded"
                self.logger.error(f"DEPLOYMENT ABORTED: {len(failed)}/{total_instances} instances failed")
                result.history.append({
                    "event": "abort",
                    "reason": result.aborted_reason,
                    "failed_count": len(failed),
                    "total_count": total_instances
                })

                # Roll back all changes
                self.logger.info("Rolling back all changes due to deployment failure")
                await self.rollback(instances, snapshot)
                result.rolled_back = True
                result.updated = []
                result.failed = failed
                result.success = False
                return updated, failed, True  # Deployment was aborted

            result.history.append({
                "event": "batch_completed",
                "batch": batch_idx,
                "updated_so_far": len(updated),
                "failed_so_far": len(failed)
            })

        return updated, failed, False  # No abort needed

    def _finish_deployment(self, result, updated, failed, desired, current):
        """Clean up and finalize deployment"""
        # Update system state to reflect desired versions
        current.code_version = desired.code_version
        current.configuration_version = desired.configuration_version

        # Set final results
        result.updated = updated
        result.failed = failed
        result.success = (len(failed) == 0)

        # Log final status
        if result.success:
            self.logger.info(f"SUCCESS: Deployment completed - {len(updated)} instances updated")
        else:
            self.logger.warning(f"PARTIAL SUCCESS: {len(updated)} updated, {len(failed)} failed")

    async def deploy(self, instances, desired, current, config, dry_run=False):
        """Main deployment method - deploy updates in batches"""
        # Check if deployment is already running
        if current.deployment_in_progress:
            error_msg = "deployment already in progress"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        self.logger.info(f"Starting deployment (dry_run={dry_run})")
        result = DeploymentResult(success=False)

        # Figure out which instances need updates
        instances_to_update, already_updated = self._find_instances_to_update(instances, desired)
        result.skipped = already_updated

        # Handle special cases
        if dry_run or len(instances_to_update) == 0:
            self._handle_dry_run_or_no_updates(result, instances_to_update, dry_run, desired, current)
            return result

        # Start actual deployment
        current.deployment_in_progress = True
        self.logger.info(f"Deploying to {len(instances_to_update)} instances in batches of {config.batch_size}")

        # Save current state in case we need to rollback
        from dataclasses import asdict
        snapshot = {}
        for instance in instances:
            snapshot[instance.instance_id] = asdict(instance)

        try:
            # Split into batches and deploy
            batches = self.plan_batches(instances_to_update, config.batch_size)
            self.logger.info(f"Created {len(batches)} batches for deployment")

            updated, failed, was_aborted = await self._run_batches(
                batches, desired, config, result, instances, snapshot
            )

            if was_aborted:
                return result

            # Finish up
            self._finish_deployment(result, updated, failed, desired, current)
            return result

        finally:
            current.deployment_in_progress = False
            self.logger.debug("Deployment lock released")
