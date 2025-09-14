# Deployment Engine

A distributed deployment system that safely rolls out updates across many service instances. Each instance has its own version of application code and configuration. This deployment engine performs controlled, failure-tolerant updates in batches with support for concurrency and rollback.

> Self-contained implementation with no external dependencies.

---

## What's Built

**Core Components:**
1. **Desired System State** - Target versions of code_version and configuration_version for all instances
2. **Current System State** - Current system state including versions and deployment progress tracking
3. **Instance/Node State** - Each service instance maintains its current versions and health status (healthy, degraded, failed)
4. **Deployment Engine** - Orchestrates deployment rollout in batches with:
   - Concurrent updates within each batch (respecting batch_size)
   - Automatic abort when failures exceed limits (total count or percentage)
   - Automatic and manual rollback capabilities
   - Prevention of concurrent deployments

**Additional Features:**
- Retry logic with exponential backoff
- Deployment timeouts
- Dry-run mode for planning
- Deployment history tracking (global & per-node)
- Simple CLI interface

## Quickstart

### Local Development
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run tests
pytest
```

### Docker (Recommended)
```bash
# Run tests
docker-compose --profile tests up --build

# Interactive CLI shell
docker-compose --profile cli up --build

# Plan deployment
docker-compose run --rm deployment-engine-cli python -m deployment_engine.cli deploy \
  --instances examples/instances.json --desired examples/desired.json --batch-size 3 --dry-run

# Deploy
docker-compose run --rm deployment-engine-cli python -m deployment_engine.cli deploy \
  --instances examples/instances.json --desired examples/desired.json --batch-size 3 --max-failures 2

# Rollback
docker-compose run --rm deployment-engine-cli python -m deployment_engine.cli rollback \
  --snapshot .snapshot.json --instances examples/instances.json
```

## CLI

```bash
# Plan only (dry-run)
python -m deployment_engine.cli deploy --instances examples/instances.json --desired examples/desired.json --batch-size 3 --dry-run

# Deploy
python -m deployment_engine.cli deploy --instances examples/instances.json --desired examples/desired.json --batch-size 3 --max-failures 2

# Manual rollback (using state snapshot file produced by a previous run)
python -m deployment_engine.cli rollback \
    --snapshot .snapshot.json \
    --instances examples/instances.json
```

> For demos, the CLI writes a `.snapshot.json` with the pre-deployment snapshot used for rollback.

## Assumptions & Design Choices

- **State in memory**: This example keeps instance state in memory and/or JSON files for clarity.
- **Per-batch concurrency**: All nodes in a batch are updated concurrently; batches run sequentially.
- **Failure injection**: Via pluggable `FailureInjector`
- **Rollback**: Restores versions & health from a snapshot of pre-deployment values.
- **Timeout and retry**: Each node update can be wrapped in a timeout; retry is per-node with exponential backoff.

## Implemented vs Skipped

- Implemented: batching, concurrent updates, thresholds, rollback (auto + manual), dry-run, timeout, retry, timeouts, basic history, simple CLI.
- Skipped: Support for different deployment strategies (canary), Handling of new nodes that join during a deployment rollout, API interface

## Rough Time Spent

~4 hours end-to-end (design + code + tests + CI).

## LLM vs handcrafted

- Core structure + core tests: handcrafted
- README + engine initial logic (copied from previous project) + additional tests: partially generated with AI assistance

## Project Layout

```
deployment_engine/
  __init__.py
  models.py
  failure.py
  engine.py
  cli.py
examples/
  instances.json
  desired.json
tests/
  test_*.py
docker-compose.yml
Dockerfile
.dockerignore
requirements.txt
README.md
```

---

Happy reviewing!
