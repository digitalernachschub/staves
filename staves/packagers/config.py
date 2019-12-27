from dataclasses import dataclass
from typing import IO, Mapping, Optional

import toml


@dataclass
class PackagingConfig:
    name: str
    command: str
    annotations: Mapping[str, str]
    version: Optional[str]


def read_packaging_config(config_file: IO) -> PackagingConfig:
    data = toml.load(config_file)
    return PackagingConfig(
        name=data["name"],
        command=data["command"],
        annotations=data.get("annotations", {}),
        version=data.get("version"),
    )
