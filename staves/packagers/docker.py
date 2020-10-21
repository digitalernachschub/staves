import io
import os
import tarfile
from typing import Mapping, Sequence

import docker


def _create_dockerfile(annotations: Mapping[str, str], *cmd: str) -> str:
    label_string = " ".join(
        [f'"{key}"="{value}"' for key, value in annotations.items()]
    )
    command_string = ", ".join(['"{}"'.format(c) for c in cmd])
    dockerfile = ""
    if label_string:
        dockerfile += "LABEL {label_string}" + os.linesep
    dockerfile += f"""\
    FROM scratch
    COPY rootfs /
    ENTRYPOINT [{command_string}]
    """
    return dockerfile


def _docker_image_from_rootfs(
    rootfs_path: str, tag: str, command: Sequence, annotations: Mapping[str, str]
):
    client = docker.from_env()
    dockerfile = _create_dockerfile(annotations, *command).encode("utf-8")
    context = io.BytesIO()
    with tarfile.open(fileobj=context, mode="w") as tar:
        dockerfile_info = tarfile.TarInfo(name="Dockerfile")
        dockerfile_info.size = len(dockerfile)
        tar.addfile(dockerfile_info, fileobj=io.BytesIO(dockerfile))
        tar.add(name=rootfs_path, arcname="rootfs")
    context.seek(0)
    client.images.build(fileobj=context, tag=tag, custom_context=True)
