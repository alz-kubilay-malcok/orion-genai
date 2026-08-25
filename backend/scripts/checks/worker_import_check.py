"""Import smoke — `python -m scripts.checks.worker_import_check`."""

from src.worker import WorkerConfig, WorkerDependencies, WorkerRunner, OutboxDispatcher
from src.worker.handlers import build_handlers
from src.worker.dependencies_factory import build_worker_dependencies


def main() -> int:
    cfg = WorkerConfig.from_env()
    print(f"config.poll_interval_seconds={cfg.poll_interval_seconds}")
    print(f"config.max_attempts={cfg.max_attempts}")

    deps = WorkerDependencies(session_factory=None)  # smoke only
    handlers = build_handlers(deps)
    print(f"handlers={sorted(handlers.keys())}")

    dispatcher = OutboxDispatcher(session_factory=None.__class__ if False else None, config=cfg, deps=deps)
    print(f"dispatcher.worker_id={dispatcher.worker_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
