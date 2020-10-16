from typing import IO

import toml

from staves.builders.gentoo import PackagingConfig


def read_packaging_config(config_file: IO) -> PackagingConfig:
    data = toml.load(config_file)
    return PackagingConfig(
        name=data["name"],
        command=data["command"],
        annotations=data.get("annotations", {}),
        version=data.get("version"),
    )
