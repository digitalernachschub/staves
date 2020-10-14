#!/usr/bin/env bash
set -e

setup_test_env() {
    echo "Setting up test environment…"
    python3.6 -m venv venv
    . venv/bin/activate
    pip install poetry
}

run_unit_tests() {
    PYTHONPATH=. pytest
}

pep440_version() {
    __pep440_version=
    local version=$1
    local version_without_commit_hash="${version%-g*}"
    local full_version="${version_without_commit_hash#*-}"
    local tag_version="${version_without_commit_hash%-*}"
    if [[ "${full_version}" == "${tag_version}" ]]; then
        # Release version
        __pep440_version="${tag_version}"
    else
        # Development version
        local commits_after_tag="${full_version##*-}"
        __pep440_version="${tag_version}.dev${commits_after_tag}"
    fi
}

project_name=$(basename $(pwd))
version=$(git describe --tags --always --dirty)
version=${version#${project_name}-}
pep440_version ${version}
setup_test_env

poetry version "${__pep440_version}"
poetry build
poetry install

#run_unit_tests

glibc_stage3_date="20190311"
full_version="${version}.${glibc_stage3_date}"
builder_name=$(staves init --staves-version "${full_version}" --stage3 "${glibc_stage3_date}")
staves build --build-cache staves-x86_64-glibc-cache  \
    --builder "${builder_name}" --create-builder --config x86_64-glibc.toml "${full_version}"

if [[ $(git tag --list ${project_name}-${version}) ]]; then
  docker tag "staves/x86_64-glibc:${full_version}" "staves/x86_64-glibc:${version}"
  docker tag "staves/x86_64-glibc:${full_version}" "staves/x86_64-glibc:${version%.*}"
  docker tag "staves/x86_64-glibc:${full_version}" "staves/x86_64-glibc:${version%%.*}"
fi

if [[ $(git tag --list ${project_name}-${version}) ]]; then
    echo "Found release version. Deploying tarball…"
    poetry publish --repository ameto
else
    echo "Found development version. Nothing to publish."
fi
