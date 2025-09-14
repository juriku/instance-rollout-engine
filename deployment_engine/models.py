from dataclasses import dataclass, field
from enum import Enum

class Health(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"

@dataclass
class InstanceState:
    instance_id: str
    code_version: str
    configuration_version: str
    health: Health = Health.HEALTHY

@dataclass
class SystemState:
    code_version: str
    configuration_version: str
    deployment_in_progress: bool = False

@dataclass
class DeploymentConfig:
    """Configuration for deployment behavior"""
    batch_size: int = 5  # How many instances to deploy at once
    max_failures: int = None  # Max failed instances before abort
    failure_percentage: float = None  # Max failure rate (0-100%) before abort
    timeout_s: float = None  # Timeout per instance update
    retry_max_attempts: int = 0  # How many times to retry failed updates
    retry_base_delay_s: float = 0.1  # Base delay between retries

@dataclass
class DeploymentResult:
    """Results from a deployment run"""
    success: bool
    updated: list = field(default_factory=list)  # Instance IDs that were successfully updated
    failed: list = field(default_factory=list)  # Instance IDs that failed to update
    skipped: list = field(default_factory=list)  # Instance IDs that were already up to date
    aborted_reason: str = None  # Why deployment was aborted (if it was)
    rolled_back: bool = False  # Whether we rolled back due to failures
    history: list = field(default_factory=list)  # Overall deployment events
    per_node_history: dict = field(default_factory=dict)  # Per-instance events

