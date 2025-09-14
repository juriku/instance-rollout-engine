import argparse
import json
import asyncio
import sys
from .models import InstanceState, SystemState, DeploymentConfig
from .engine import DeploymentEngine
from .logger import setup_logging, get_logger


def load_instances(path):
    logger = get_logger("cli")
    try:
        data = json.load(open(path))
        instances = []
        for i in data:
            health = i.get("health", "healthy")
            instance = InstanceState(
                instance_id=i["instance_id"],
                code_version=i["code_version"],
                configuration_version=i["configuration_version"],
                health=health
            )
            instances.append(instance)
        return instances
    except Exception as e:
        logger.error(f"Error loading instances: {e}")
        raise


def save_instances(path, instances):
    from dataclasses import asdict
    json.dump([asdict(i) for i in instances], open(path, "w"), indent=2)


def main():
    parser = argparse.ArgumentParser(description="Deployment engine")
    parser.add_argument("--log-level", default="INFO")
    sub = parser.add_subparsers(dest="cmd", required=True)

    deploy = sub.add_parser("deploy")
    deploy.add_argument("--instances", required=True)
    deploy.add_argument("--desired", required=True)
    deploy.add_argument("--batch-size", type=int, default=5)
    deploy.add_argument("--max-failures", type=int)
    deploy.add_argument("--dry-run", action="store_true")

    rollback = sub.add_parser("rollback")
    rollback.add_argument("--snapshot", required=True)
    rollback.add_argument("--instances")

    args = parser.parse_args()
    setup_logging(args.log_level)

    if args.cmd == "deploy":
        try:
            instances = load_instances(args.instances)
            desired = SystemState(**json.load(open(args.desired)))
            current = SystemState(instances[0].code_version, instances[0].configuration_version)
            config = DeploymentConfig(args.batch_size, args.max_failures)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

        # Save snapshot
        from dataclasses import asdict
        json.dump({i.instance_id: asdict(i) for i in instances}, open(".snapshot.json", "w"), indent=2)

        async def run():
            result = await DeploymentEngine().deploy(instances, desired, current, config, args.dry_run)
            print(json.dumps(asdict(result), indent=2))
            if not args.dry_run:
                save_instances(args.instances, instances)

        asyncio.run(run())

    if args.cmd == "rollback":
        try:
            snapshot = json.load(open(args.snapshot))
            instances = load_instances(args.instances) if args.instances else load_instances("examples/instances.json")
            asyncio.run(DeploymentEngine().rollback(instances, snapshot))
            if args.instances:
                save_instances(args.instances, instances)
            print("Done.")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
