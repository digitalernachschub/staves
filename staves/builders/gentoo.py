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
from pathlib import Path
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


@dataclass
class PackagingConfig:
    name: str
    command: str
    annotations: Mapping[str, str]
    version: Optional[str]


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


@dataclass
class Locale:
    name: str
    charset: str


@dataclass
class Repository:
    name: str
    uri: str
    sync_type: str


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

    def add_repository(self, repository: Repository):
        logger.info(f"Adding repository {repository.name}")
        repository_config_path = Path("/etc/portage/repos.conf") / repository.name
        repository_config = f"""\
        [{repository.name}]
        location = /var/db/repos/{repository.name}
        sync-type = {repository.sync_type}
        sync-uri = {repository.uri}
        """
        repository_config_path.write_text(repository_config)
        self.update_repository(repository.name)

    def update_repository(self, name: str):
        run_and_log_error(["emaint", "sync", "--repo", name])

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
    build_env.write_env(
        {
            "FEATURES": "${FEATURES} -userpriv -usersandbox "
            "-ipc-sandbox -network-sandbox -pid-sandbox -sandbox "
            "buildpkg binpkg-multi-instance -binpkg-logs "
            "-news nodoc noinfo noman"
        }
    )
    if image_spec.global_env:
        build_env.write_env(image_spec.global_env)
    if image_spec.package_envs:
        for env_name, env in image_spec.package_envs.items():
            build_env.write_env(name=env_name, env_vars=env)
    if image_spec.repositories:
        for repository in image_spec.repositories:
            build_env.add_repository(repository)
    for package, package_config in image_spec.package_configs.items():
        build_env.write_package_config(package, **package_config)
    packages = list(image_spec.packages_to_be_installed)
    if config.libc:
        packages.append("virtual/libc")
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


def _deserialize_image_spec(data: bytes) -> ImageSpec:
    image_spec_json = json.loads(data)
    return ImageSpec(
        locale=Locale(**image_spec_json["locale"]),
        global_env=image_spec_json["global_env"],
        package_envs=image_spec_json["package_envs"],
        repositories=[
            Repository(**repository) for repository in image_spec_json["repositories"]
        ],
        package_configs=image_spec_json["package_configs"],
        packages_to_be_installed=image_spec_json["packages_to_be_installed"],
    )


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stdlib",
        dest="stdlib",
        action="store_true",
        help="Copy stdlib into target image",
    )
    parser.add_argument(
        "--no-stdlib",
        dest="stdlib",
        action="store_false",
        help="Do not copy stdlib into target image",
    )
    parser.set_defaults(stdlib=False)
    args = parser.parse_args()

    content_length = struct.unpack(">Q", sys.stdin.buffer.read(8))[0]
    print(f"Reading {content_length} bytes…")
    content = sys.stdin.buffer.read(content_length)
    print(f"Deserializing content")
    image_spec = _deserialize_image_spec(content)
    emerge_info = subprocess.run(
        ["emerge", "--info"], stdout=subprocess.PIPE, check=True
    )
    elibc_match = re.search(rb'ELIBC="([^"]+)"', emerge_info.stdout)
    elibc = elibc_match.group(1).decode()
    if elibc == "glibc":
        libc = Libc.glibc
    elif elibc == "musl":
        libc = Libc.musl
    else:
        raise StavesError(f"Unsupported ELIBC: {elibc}")
    build(
        image_spec,
        config=BuilderConfig(libc=libc),
        stdlib=args.stdlib,
    )
