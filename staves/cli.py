"""Installs Gentoo portage packages into a specified directory."""

import logging
from pathlib import Path
from typing import IO, MutableMapping, Any, Sequence

import click
import toml

import staves.runtimes.docker as run_docker
from staves.builders.gentoo import (
    BuilderConfig,
    Environment,
    ImageSpec,
    Libc,
    Locale,
    Repository,
)
from staves.packagers.config import read_packaging_config
from staves.packagers.docker import package


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


@cli.command(help="Initializes a builder for the specified runtime")
@click.option("--version", default="latest")
@click.option("--stage3", default="latest", show_default=True)
@click.option("--portage-snapshot", default="latest", show_default=True)
@click.option(
    "--libc", type=click.Choice(["glibc", "musl"]), default="glibc", show_default=True
)
def init(version, stage3, portage_snapshot, libc):
    from staves.runtimes.docker import bootstrap

    click.echo("Bootstrapping builder images…")
    builder_name = bootstrap(version, stage3, portage_snapshot, libc)
    click.echo(builder_name)


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
    "--create-builder",
    is_flag=True,
    default=False,
    help="When a builder is created, Staves will copy files such as the Portage tree, make.conf and make.profile.",
)
@click.option(
    "--jobs", type=int, help="Number of concurrent jobs executed by the builder"
)
@click.option("--builder", help="The name of the builder to be used")
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
def build(
    config,
    libc,
    create_builder,
    stdlib,
    jobs,
    builder,
    build_cache,
    ssh,
    netrc,
    locale,
):
    libc_enum = Libc.musl if "musl" in libc else Libc.glibc
    builder_config = BuilderConfig(concurrent_jobs=jobs, libc=libc_enum)
    image_spec = _read_image_spec(config)

    run_docker.run(
        builder,
        builder_config,
        stdlib,
        create_builder,
        build_cache,
        image_spec,
        ssh=ssh,
        netrc=netrc,
        env={"LANG": locale},
    )


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
@click.option("--version", help="Version number of the packaged artifact")
@click.option("--config", type=click.Path(dir_okay=False, exists=True))
@click.option(
    "--packaging",
    type=click.Choice(["none", "docker"]),
    default="docker",
    help="Packaging format of the resulting image",
)
def package(rootfs_path, version, config, packaging):
    config_path = Path(str(config)) if config else Path("staves.toml")
    if not config_path.exists():
        raise StavesError(f'No configuration file found at path "{str(config_path)}"')
    with config_path.open(mode="r") as config_file:
        packaging_config = read_packaging_config(config_file)
    if version:
        packaging_config.version = version

    if packaging == "docker":
        package(
            rootfs_path,
            packaging_config.name,
            packaging_config.version,
            packaging_config.command,
            packaging_config.annotations,
        )


def main():
    cli.main(standalone_mode=False)


if __name__ == "__main__":
    main()
