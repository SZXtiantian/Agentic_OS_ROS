from pathlib import Path


def repo_root_from_cwd() -> Path:
    cwd = Path.cwd().resolve()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "configs").is_dir():
            return candidate
    return cwd


def default_config_path(filename: str) -> Path:
    opt_path = Path("/opt/agentic/etc") / filename
    if opt_path.exists():
        return opt_path
    return repo_root_from_cwd() / "configs" / filename
