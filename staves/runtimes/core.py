from staves.builders.gentoo import build, BuilderConfig
from staves.core import ImageSpec, Libc, StavesError


def run(
    image_spec: ImageSpec,
    libc: Libc,
    root_path: str,
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

    builder_config = BuilderConfig(image_path=root_path, concurrent_jobs=jobs)
    build(
        image_spec, builder_config, libc, create_builder, stdlib,
    )
