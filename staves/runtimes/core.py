from staves.builders.gentoo import build, BuilderConfig
from staves.builders.gentoo import ImageSpec


class StavesError(Exception):
    pass


def run(
    image_spec: ImageSpec,
    builder_config: BuilderConfig,
    create_builder: bool,
    stdlib: bool,
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
        image_spec,
        builder_config,
        create_builder,
        stdlib,
    )
