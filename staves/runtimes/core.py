from typing import Any, IO, Mapping, MutableMapping, Sequence

import toml
from dataclasses import dataclass

from staves.builders.gentoo import build, Environment, Locale, Repository
from staves.core import Libc, StavesError


@dataclass
class ImageSpec:
    name: str
    command: str
    annotations: Mapping[str, str]
    global_env: Environment
    package_envs: Mapping[str, Environment]
    repositories: Sequence[Repository]
    locale: Locale
    package_configs: Mapping[str, Mapping]
    packages_to_be_installed: Sequence[str]


def run(
    image_spec: ImageSpec,
    libc: Libc,
    root_path: str,
    packaging: str,
    version: str,
    create_builder: bool,
    stdlib: bool,
    name: str = None,
    jobs: int = None,
    ssh: bool = True,
    netrc: bool = True,
    update_repos: Sequence[str] = None,
):
    if not ssh:
        raise StavesError(
            "Default runtime does not have any filesystem isolation. Therefore, it is not possible not "
            "to use the user's ssh keys"
        )
    if not netrc:
        raise StavesError(
            "Default runtime does not have any filesystem isolation. Therefore, it is not possible not "
            "to use the user's netrc configuration"
        )

    name = name or image_spec.name
    build(
        image_spec.locale,
        image_spec.package_configs,
        list(image_spec.packages_to_be_installed),
        libc,
        root_path,
        create_builder,
        stdlib,
        global_env=image_spec.global_env,
        package_envs=image_spec.package_envs,
        repositories=image_spec.repositories,
        max_concurrent_jobs=jobs,
        update_repos=update_repos,
    )
    if packaging == "docker":
        from staves.packagers.docker import package

        package(root_path, name, version, image_spec.command, image_spec.annotations)


def _read_image_spec(config_file: IO) -> ImageSpec:
    config = toml.load(config_file)
    env = config.pop("env") if "env" in config else None
    package_configs = {k: v for k, v in config.items() if isinstance(v, dict)}
    packages_to_be_installed = [*config.get("packages", [])]
    return ImageSpec(
        name=config["name"],
        command=config["command"],
        annotations=config.get("annotations", {}),
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
