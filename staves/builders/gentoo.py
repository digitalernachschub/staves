import glob
import json
import logging
import multiprocessing
import os
import re
import shutil
import struct
import subprocess
from enum import Enum, auto

from dataclasses import dataclass, field
from typing import (
    Mapping,
    NewType,
    Optional,
    Sequence,
)


logger = logging.getLogger(__name__)


Environment = NewType("Environment", Mapping[str, str])


class Libc(Enum):
    glibc = auto()
    musl = auto()


@dataclass
class BuilderConfig:
    libc: Libc
    concurrent_jobs: int = None


class StavesError(Exception):
    pass


class RootfsError(StavesError):
    pass


def _create_rootfs(
    rootfs_path, *packages, max_concurrent_jobs: int = 1, max_cpu_load: int = 1
):
    logger.info(
        "Creating rootfs at {} containing the following packages:".format(rootfs_path)
    )
    logger.info(", ".join(packages))

    logger.debug("Installing build-time dependencies to builder")
    emerge_env = os.environ
    emerge_env["MAKEOPTS"] = "-j{} -l{}".format(max_concurrent_jobs, max_cpu_load)
    # --emptytree is needed, because build dependencies of runtime dependencies are ignored by --root-deps=rdeps
    # (even when --with-bdeps=y is passed). By adding --emptytree, we get a binary package that can be installed to rootfs
    emerge_bdeps_command = [
        "emerge",
        "--verbose",
        "--onlydeps",
        "--usepkg",
        "--with-bdeps=y",
        "--emptytree",
        "--jobs",
        str(max_concurrent_jobs),
        "--load-average",
        str(max_cpu_load),
        *packages,
    ]
    emerge_bdeps_call = subprocess.run(
        emerge_bdeps_command, stderr=subprocess.PIPE, env=emerge_env
    )
    if emerge_bdeps_call.returncode != 0:
        logger.error(emerge_bdeps_call.stderr)
        raise RootfsError("Unable to install build-time dependencies.")

    logger.debug("Installing runtime dependencies to rootfs")
    emerge_rdeps_command = [
        "emerge",
        "--verbose",
        "--root={}".format(rootfs_path),
        "--root-deps=rdeps",
        "--oneshot",
        "--usepkg",
        "--jobs",
        str(max_concurrent_jobs),
        "--load-average",
        str(max_cpu_load),
        *packages,
    ]
    emerge_rdeps_call = subprocess.run(
        emerge_rdeps_command, stderr=subprocess.PIPE, env=emerge_env
    )
    if emerge_rdeps_call.returncode != 0:
        logger.error(emerge_rdeps_call.stderr)
        raise RootfsError("Unable to install runtime dependencies.")


def _max_cpu_load() -> int:
    return multiprocessing.cpu_count()


def _max_concurrent_jobs() -> int:
    return _max_cpu_load() + 1


def _copy_stdlib(rootfs_path: str, copy_libstdcpp: bool):
    libgcc = "libgcc_s.so.1"
    libstdcpp = "libstdc++.so.6"
    search_path = os.path.join("/usr", "lib", "gcc")
    libgcc_path = None
    libstdcpp_path = None
    for directory_path, subdirs, files in os.walk(search_path):
        if libgcc in files:
            libgcc_path = os.path.join(directory_path, libgcc)
        if libstdcpp in files:
            libstdcpp_path = os.path.join(directory_path, libstdcpp)
    if libgcc_path is None:
        raise StavesError("Unable to find " + libgcc + " in " + search_path)
    shutil.copy(libgcc_path, os.path.join(rootfs_path, "usr", "lib"))
    if copy_libstdcpp:
        if libstdcpp_path is None:
            raise StavesError("Unable to find " + libstdcpp + " in " + search_path)
        shutil.copy(libstdcpp_path, os.path.join(rootfs_path, "usr", "lib"))


def _update_builder(max_concurrent_jobs: int = 1, max_cpu_load: int = 1):
    # Register staves in /var/lib/portage/world
    register_staves = subprocess.run(
        ["emerge", "--noreplace", "dev-util/staves"], stderr=subprocess.PIPE
    )
    if register_staves.returncode != 0:
        logger.error(register_staves.stderr)
        raise RootfsError("Unable to register Staves as an installed package")

    emerge_env = os.environ
    emerge_env["MAKEOPTS"] = "-j{} -l{}".format(max_concurrent_jobs, max_cpu_load)
    update_world = subprocess.run(
        [
            "emerge",
            "--verbose",
            "--deep",
            "--usepkg",
            "--with-bdeps=y",
            "--jobs",
            str(max_concurrent_jobs),
            "--load-average",
            str(max_cpu_load),
            "@world",
        ],
        stderr=subprocess.PIPE,
        env=emerge_env,
    )
    if update_world.returncode != 0:
        logger.error(update_world.stderr)
        raise RootfsError("Unable to update builder environment")


def _copy_to_rootfs(rootfs: str, path_glob: str):
    globs = glob.iglob(path_glob)
    for host_path in globs:
        rootfs_path = os.path.join(rootfs, os.path.relpath(host_path, "/"))
        os.makedirs(os.path.dirname(rootfs_path), exist_ok=True)
        if os.path.islink(
            host_path
        ):  # Needs to be checked first, because other methods follow links
            link_target = os.readlink(host_path)
            os.symlink(link_target, rootfs_path)
        elif os.path.isdir(host_path):
            shutil.copytree(host_path, rootfs_path)
        elif os.path.isfile(host_path):
            shutil.copy(host_path, rootfs_path)
        else:
            raise StavesError(
                "Copying {} to rootfs is not supported.".format(path_glob)
            )


def libc_to_package_name(libc: Libc) -> str:
    if libc == Libc.glibc:
        return "sys-libs/glibc"
    elif libc == Libc.musl:
        return "sys-libs/musl"
    else:
        raise ValueError(f"Unsupported value for libc: {libc}")


@dataclass
class Locale:
    name: str
    charset: str


@dataclass
class Repository:
    name: str
    sync_type: Optional[str] = None
    uri: Optional[str] = None


def run_and_log_error(cmd: Sequence[str]) -> int:
    cmd = subprocess.run(
        cmd, universal_newlines=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    if cmd.returncode != 0:
        logger.error(cmd.stderr)
        raise StavesError(f"Command failed: {cmd}")
    return cmd.returncode


class BuildEnvironment:
    def __init__(self):
        os.makedirs("/etc/portage/repos.conf", exist_ok=True)
        logger.info(f"Updating repository list")
        run_and_log_error(["eselect", "repository", "list", "-i"])

    def add_repository(self, name: str, sync_type: str = None, uri: str = None):
        logger.info(f"Adding repository {name}")
        if uri and sync_type:
            add_repo_command = ["eselect", "repository", "add", name, sync_type, uri]
        else:
            add_repo_command = ["eselect", "repository", "enable", name]
        run_and_log_error(add_repo_command)
        self.update_repository(name)

    def update_repository(self, name: str):
        run_and_log_error(["emaint", "sync", "--repo", name])

    @property
    def repositories(self) -> Sequence[str]:
        list_repos_call = subprocess.run(
            ["eselect", "repository", "list", "-i"],
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if list_repos_call.returncode != 0:
            logger.error(list_repos_call.stderr)
            raise StavesError("Failed to retrieve a list of available repositories")
        repositories = []
        repo_name_pattern = re.compile(r"\s*\[\d+\]\s*(\S+)")
        for line in list_repos_call.stdout.splitlines()[1:]:
            match = repo_name_pattern.match(line)
            if match:
                repositories.append(match.group(1))
        return repositories

    def write_package_config(
        self,
        package: str,
        env: Sequence[str] = None,
        keywords: Sequence[str] = None,
        use: Sequence[str] = None,
    ):
        if env:
            package_config_path = os.path.join(
                "/etc", "portage", "package.env", *package.split("/")
            )
            os.makedirs(os.path.dirname(package_config_path), exist_ok=True)
            with open(package_config_path, "w") as f:
                package_environments = " ".join(env)
                f.write("{} {}{}".format(package, package_environments, os.linesep))
        if keywords:
            package_config_path = os.path.join(
                "/etc", "portage", "package.accept_keywords", *package.split("/")
            )
            os.makedirs(os.path.dirname(package_config_path), exist_ok=True)
            with open(package_config_path, "w") as f:
                package_keywords = " ".join(keywords)
                f.write("{} {}{}".format(package, package_keywords, os.linesep))
        if use:
            package_config_path = os.path.join(
                "/etc", "portage", "package.use", *package.split("/")
            )
            os.makedirs(os.path.dirname(package_config_path), exist_ok=True)
            with open(package_config_path, "w") as f:
                package_use_flags = " ".join(use)
                f.write("{} {}{}".format(package, package_use_flags, os.linesep))

    def write_env(self, env_vars, name=None):
        os.makedirs("/etc/portage/env", exist_ok=True)
        if name:
            conf_path = os.path.join("/etc", "portage", "env", name)
        else:
            conf_path = os.path.join("/etc", "portage", "make.conf")
        with open(conf_path, "a") as make_conf:
            make_conf.writelines(
                ('{}="{}"{}'.format(k, v, os.linesep) for k, v in env_vars.items())
            )


@dataclass
class ImageSpec:
    locale: Locale
    global_env: Environment = field(default_factory=lambda: Environment({}))
    package_envs: Mapping[str, Environment] = field(default_factory=dict)
    repositories: Sequence[Repository] = field(default_factory=list)
    package_configs: Mapping[str, Mapping] = field(default_factory=dict)
    packages_to_be_installed: Sequence[str] = field(default_factory=list)


def build(
    image_spec: ImageSpec,
    config: BuilderConfig,
    stdlib: bool,
):
    rootfs_path = "/tmp/rootfs"
    build_env = BuildEnvironment()
    if image_spec.global_env:
        build_env.write_env(image_spec.global_env)
    if image_spec.package_envs:
        for env_name, env in image_spec.package_envs.items():
            build_env.write_env(name=env_name, env_vars=env)
    if image_spec.repositories:
        for repository in image_spec.repositories:
            build_env.add_repository(
                repository.name, repository.sync_type, repository.uri
            )
    logger.debug(
        "The following repositories are available for the build: "
        + ", ".join(build_env.repositories)
    )
    for package, package_config in image_spec.package_configs.items():
        build_env.write_package_config(package, **package_config)
    packages = list(image_spec.packages_to_be_installed)
    if config.libc:
        packages.append(libc_to_package_name(config.libc))
    if config.libc != Libc.musl:
        # This value should depend on the selected profile, but there is currently no musl profile with
        # links to lib directories.
        for prefix in ["", "usr", "usr/local"]:
            lib_prefix = os.path.join(rootfs_path, prefix)
            lib_path = os.path.join(lib_prefix, "lib64")
            os.makedirs(lib_path, exist_ok=True)
            os.symlink("lib64", os.path.join(lib_prefix, "lib"))
    concurrent_jobs = config.concurrent_jobs or _max_concurrent_jobs()
    _create_rootfs(
        rootfs_path,
        *packages,
        max_concurrent_jobs=concurrent_jobs,
        max_cpu_load=_max_cpu_load(),
    )
    _copy_stdlib(rootfs_path, copy_libstdcpp=stdlib)
    if config.libc == Libc.glibc:
        with open(os.path.join("/etc", "locale.gen"), "a") as locale_conf:
            locale_conf.writelines(
                "{} {}".format(image_spec.locale.name, image_spec.locale.charset)
            )
            subprocess.run("locale-gen")
        _copy_to_rootfs(rootfs_path, "/usr/lib/locale/locale-archive")


if __name__ == "__main__":
    import sys

    content_length = struct.unpack(">Q", sys.stdin.buffer.read(8))[0]
    print(f"Reading {content_length} bytes…")
    content = sys.stdin.buffer.read(content_length)
    print(f"Deserializing content")
    image_spec_json = json.loads(content)
    image_spec = ImageSpec(
        locale=Locale(**image_spec_json["locale"]),
        global_env=image_spec_json["global_env"],
        package_envs=image_spec_json["package_envs"],
        repositories=[
            Repository(**repository) for repository in image_spec_json["repositories"]
        ],
        package_configs=image_spec_json["package_configs"],
        packages_to_be_installed=image_spec_json["packages_to_be_installed"],
    )
    build(
        image_spec,
        config=BuilderConfig(libc=Libc.glibc),
        stdlib=True,
    )
