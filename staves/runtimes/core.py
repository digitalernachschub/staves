from typing import IO

import toml

from staves.builders.gentoo import build
from staves.types import Libc


def run(config_file: IO, libc: Libc, root_path: str, packaging: str, version: str,
        create_builder: bool, stdlib: bool, name: str=None, jobs: int=None):
    config = toml.load(config_file)
    if not name:
        name = config['name']
    env = config.pop('env') if 'env' in config else None
    repositories = config.pop('repositories') if 'respositories' in config else None
    locale = config.pop('locale') if 'locale' in config else {'name': 'C', 'charset': 'UTF-8'}
    package_configs = {k: v for k, v in config.items() if isinstance(v, dict)}
    packages_to_be_installed = [*config.get('packages', [])]
    build(name, locale, package_configs, packages_to_be_installed, libc, root_path, packaging, version, create_builder,
          stdlib, annotations=config.get('annotations', {}), env=env, repositories=repositories, command=config['command'],
          max_concurrent_jobs=jobs)
