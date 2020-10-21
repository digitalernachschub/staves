"""Installs Gentoo portage packages into a specified directory."""

import io
import logging
import os
import tarfile
from pathlib import Path
from typing import IO, MutableMapping, Any, Sequence

import click
import docker
import toml

import staves.runtimes.docker as run_docker
from staves.builders.gentoo import (
    BuilderConfig,
    Environment,
    ImageSpec,
    Libc,
    Locale,
    PackagingConfig,
    Repository,
)
from staves.packagers.docker import package, _create_dockerfile


logger = logging.getLogger(__name__)


class StavesError(Exception):
    pass


@click.group(name="staves")
@click.option(
    "--log-level",
    type=click.Choice(["error", "warning", "info", "debug"]),
    default="info",
)
def cli(log_level: str):
    log_level = logging.getLevelName(log_level.upper())
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)


@cli.command(help="Installs the specified packages into to the desired location.")
@click.option("--config", type=click.File(), default="staves.toml")
@click.option(
    "--libc",
    type=click.Choice(["glibc", "musl"]),
    default="glibc",
    help="Libc to be installed into rootfs",
)
@click.option("--stdlib", is_flag=True, help="Copy libstdc++ into rootfs")
@click.option(
    "--jobs", type=int, help="Number of concurrent jobs executed by the builder"
)
@click.option("--builder", help="The name of the builder to be used")
@click.option(
    "--portage",
    default="gentoo/portage",
    show_default=True,
    help="The Portage image to be used",
)
@click.option(
    "--build-cache", help="The name of the cache volume for the Docker runtime"
)
@click.option(
    "--ssh/--no-ssh",
    is_flag=True,
    default=True,
    help="Use this user's ssh identity for the builder",
)
@click.option(
    "--netrc/--no-netrc",
    is_flag=True,
    default=True,
    help="Use this user's netrc configuration in the builder",
)
@click.option(
    "--locale",
    default="C.UTF-8",
    help="Specifies the locale (LANG env var) to be set in the builder",
)
@click.option(
    "--image-path",
    default=os.path.join(os.getcwd(), "staves_root.tar"),
    help="Path to the image archive",
)
@click.option(
    "--version",
    default="latest",
    show_default=True,
    help="Version number of the packaged artifact",
)
def build(
    config,
    libc,
    stdlib,
    jobs,
    builder,
    portage,
    build_cache,
    ssh,
    netrc,
    locale,
    image_path,
    version,
):
    image_spec = _read_image_spec(config)
    image_path = Path(image_path)
    if image_path.exists():
        raise click.Abort(
            "The path to the image root already exists. For safety reasons, please remove "
            + str(image_path)
        )
    run_docker.run(
        builder,
        portage,
        build_cache,
        image_spec,
        image_path,
        stdlib=stdlib,
        ssh=ssh,
        netrc=netrc,
        env={"LANG": locale},
    )
    config.seek(0)
    packaging_config = _read_packaging_config(config)
    packaging_config.version = packaging_config.version or version
    tag = "{}:{}".format(packaging_config.name, packaging_config.version)

    client = docker.from_env()
    dockerfile = _create_dockerfile(
        packaging_config.annotations, *packaging_config.command
    ).encode("utf-8")
    with tarfile.open(str(image_path), mode="a") as tar:
        dockerfile_info = tarfile.TarInfo(name="Dockerfile")
        dockerfile_info.size = len(dockerfile)
        tar.addfile(dockerfile_info, fileobj=io.BytesIO(dockerfile))
    with open(str(image_path), "rb") as context:
        client.images.build(fileobj=context, tag=tag, custom_context=True)


def _read_image_spec(config_file: IO) -> ImageSpec:
    config = toml.load(config_file)
    env = config.pop("env") if "env" in config else {}
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
    return Locale(l["name"], l["charset"])


@cli.command("package", help="Creates a container image from a directory")
@click.argument("rootfs_path")
@click.option(
    "--version",
    default="latest",
    show_default=True,
    help="Version number of the packaged artifact",
)
@click.option("--config", type=click.Path(dir_okay=False, exists=True))
def package_(rootfs_path, version, config):
    config_path = Path(str(config)) if config else Path("staves.toml")
    if not config_path.exists():
        raise StavesError(f'No configuration file found at path "{str(config_path)}"')
    with config_path.open(mode="r") as config_file:
        packaging_config = _read_packaging_config(config_file)
    packaging_config.version = packaging_config.version or version

    package(
        rootfs_path,
        packaging_config.name,
        packaging_config.version,
        packaging_config.command,
        packaging_config.annotations,
    )


def _read_packaging_config(config_file: IO) -> PackagingConfig:
    data = toml.load(config_file)
    return PackagingConfig(
        name=data["name"],
        command=data["command"],
        annotations=data.get("annotations", {}),
        version=data.get("version"),
    )


def main():
    cli.main(standalone_mode=False)


if __name__ == "__main__":
    main()
