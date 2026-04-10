from __future__ import annotations

from ..core.discovery import discover_models, discover_resources, find_repo_root, service_names, topology_name
from ..core.output import print_kv, print_table


def config(models: bool = False, resources: bool = False) -> None:
    repo_root = find_repo_root()
    if models:
        print_table("Configured Models", ("Service", "Model"), discover_models(repo_root).items())
        return
    if resources:
        resource_rows = [
            (service, values.get("memory", ""), values.get("cpus", ""))
            for service, values in discover_resources(repo_root).items()
        ]
        print_table("Compose Resources", ("Service", "Memory", "CPUs"), resource_rows)
        return
    print_kv(
        "Platform Config",
        [
            ("repo_root", repo_root),
            ("topology", topology_name(repo_root)),
            ("services", ", ".join(service_names(repo_root))),
            ("models", ", ".join(f"{service}={model}" for service, model in discover_models(repo_root).items())),
        ],
    )
