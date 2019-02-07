from typing import Any, IO, MutableMapping, Sequence

import toml

from staves.builders.gentoo import build, Locale, Repository
from staves.types import Libc, StavesError


def run(config_file: IO, libc: Libc, root_path: str, packaging: str, version: str,
        create_builder: bool, stdlib: bool, name: str=None, jobs: int=None, ssh: bool=True, netrc: bool=True):
    if not ssh:
        raise StavesError('Default runtime does not have any filesystem isolation. Therefore, it is not possible not '
                          'to use the user\'s ssh keys')
    if not netrc:
        raise StavesError('Default runtime does not have any filesystem isolation. Therefore, it is not possible not '
                          'to use the user\'s netrc configuration')
    config = toml.load(config_file)
    if not name:
        name = config['name']
    env = config.pop('env') if 'env' in config else None
    repositories = _parse_repositories(config)
    locale = _parse_locale(config)
    package_configs = {k: v for k, v in config.items() if isinstance(v, dict)}
    packages_to_be_installed = [*config.get('packages', [])]
    build(locale, package_configs, packages_to_be_installed, libc, root_path, create_builder, stdlib, env=env,
          repositories=repositories, max_concurrent_jobs=jobs)
    if packaging == 'docker':
        from staves.packagers.docker import package
        package(root_path, name, version, config['command'], config.get('annotations', {}))


def _parse_repositories(config: MutableMapping[str, Any]) -> Sequence[Repository]:
    if 'repositories' not in config:
        return []
    repos = config.pop('repositories')
    return [Repository(r['name'], sync_type=r.get('type'), uri=r.get('uri')) for r in repos]


def _parse_locale(config: MutableMapping[str, Any]) -> Locale:
    if 'locale' not in config:
        return Locale('C', 'UTF-8')
    l = config.pop('locale')
    return Locale[l['name'], l['charset']]
