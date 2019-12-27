from staves.builders.gentoo import build
from staves.core import ImageSpec, Libc, StavesError


def run(
    image_spec: ImageSpec,
    libc: Libc,
    root_path: str,
    packaging: str,
    version: str,
    create_builder: bool,
    stdlib: bool,
    jobs: int = None,
    ssh: bool = True,
    netrc: bool = True,
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
    )
    if packaging == "docker":
        from staves.packagers.docker import package

        package(
            root_path,
            image_spec.name,
            version,
            image_spec.command,
            image_spec.annotations,
        )
