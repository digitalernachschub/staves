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

create_stage3_image() {
    local build_date="$1"
    stage3_filename=stage3-amd64-musl-hardened-${build_date}.tar.bz2
    stage3_path=/tmp/${stage3_filename}
    if [ ! -f ${stage3_path} ]; then
        wget -O ${stage3_path} http://distfiles.gentoo.org/experimental/amd64/musl/${stage3_filename}
    fi
    mkdir gentoo
    fakeroot tar xpjf ${stage3_path} -C gentoo
    docker build --tag staves/gentoo-stage3-amd64-musl-hardened:${build_date} --tag staves/gentoo-stage3-amd64-musl-hardened:latest -f Dockerfile.stage3 .
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

portage_snapshot="20190127"
#musl_stage3_date="20190104"
#create_stage3_image ${musl_stage3_date}
#full_version="${version}.${musl_stage3_date}"
#builder_name=$(staves init --staves-version "${full_version}" --libc musl --stage3 "${musl_stage3_date}" --portage-snapshot "${portage_snapshot}")
#staves build --runtime-docker-build-cache staves-x86_64-musl-cache \
#    --builder "${builder_name}" --create-builder --libc "musl" \
#    --config x86_64-musl.toml "${full_version}"
#if [[ $(git tag --list ${project_name}-${version}) ]]; then
#  docker tag "staves/x86_64-musl:${full_version}" "staves/x86_64-musl:${version}"
#  docker tag "staves/x86_64-musl:${full_version}" "staves/x86_64-musl:${version%.*}"
#  docker tag "staves/x86_64-musl:${full_version}" "staves/x86_64-musl:${version%%.*}"
#fi

glibc_stage3_date="20190104"
full_version="${version}.${glibc_stage3_date}"
builder_name=$(staves init --staves-version "${full_version}" --stage3 "${glibc_stage3_date}" --portage-snapshot "${portage_snapshot}")
staves build --runtime-docker-build-cache staves-x86_64-glibc-cache  \
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
