from enum import auto, Enum
from typing import Mapping, Sequence, IO, MutableMapping, Any

import toml
from dataclasses import dataclass, field

from builders.gentoo import Environment, Repository, Locale


class Libc(Enum):
    glibc = auto()
    musl = auto()


class StavesError(Exception):
    pass


@dataclass
class ImageSpec:
    locale: Locale
    global_env: Environment = field(default_factory=lambda: Environment({}))
    package_envs: Mapping[str, Environment] = field(default_factory=dict)
    repositories: Sequence[Repository] = field(default_factory=list)
    package_configs: Mapping[str, Mapping] = field(default_factory=dict)
    packages_to_be_installed: Sequence[str] = field(default_factory=list)


def _read_image_spec(config_file: IO) -> ImageSpec:
    config = toml.load(config_file)
    env = config.pop("env") if "env" in config else None
    package_configs = {k: v for k, v in config.items() if isinstance(v, dict)}
    packages_to_be_installed = [*config.get("packages", [])]
    return ImageSpec(
        global_env=Environment(
            {k: v for k, v in env.items() if not isinstance(v, dict)}
        ),
        package_envs={k: Environment(v) for k, v in env.items() if isinstance(k, dict)},
        repositories=_parse_repositories(config),
        locale=_parse_locale(config),
        package_configs=package_configs,
        packages_to_be_installed=packages_to_be_installed,
    )


def _parse_repositories(config: MutableMapping[str, Any]) -> Sequence[Repository]:
    if "repositories" not in config:
        return []
    repos = config.pop("repositories")
    return [
        Repository(r["name"], sync_type=r.get("type"), uri=r.get("uri")) for r in repos
    ]


def _parse_locale(config: MutableMapping[str, Any]) -> Locale:
    if "locale" not in config:
        return Locale("C", "UTF-8")
    l = config.pop("locale")
    return Locale[l["name"], l["charset"]]
