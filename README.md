# Staves
Staves is a container image builder based on the _[Portage](https://wiki.gentoo.org/wiki/Portage)_ package manager for Gentoo Linux. Staves leverages Gentoo's infrastructure to build highly customized images optimized for image size, speed, and security.

_Staves is in alpha status and is not recommended for production use_

## Features
* Minimal dependencies result in small image sizes and reduced attack surface
* [Feature toggles](https://wiki.gentoo.org/wiki/USE_flag) provide even more fine-grained control over image size and attack surface
* Full control over the build process (e.g. [compiler settings](https://wiki.gentoo.org/wiki/GCC_optimization) allows for images customized to a specific Platform or CPU
* Access to [hardened build toolchains](https://wiki.gentoo.org/wiki/Project:Hardened) with things like PIC (Position Independent Code) and SSP (Stack Smashing Protection)

## Table of Contents
* [Installation](#installation)
* [Getting Started](#getting-started)
    * [Customizing the Image](#customizing-the-image)
    * [Package-specific configuration](#package-specific-configuration)
    * [Build environment customization](#build-environment-customization)
* [How to build images based on musl libc](#how-to-build-images-based-on-musl-libc)
* [Comparison to other tools](#comparison-to-other-tools)
    * [Docker multistage builds](#docker-multistage-builds)
    * [Buildkit, buildctl, img, buildx](#buildkit-buildctl-img-buildx)
    * Kaniko, makisu
    * buildah
    * Bazel

## Installation
Staves is not available via PyPI at the moment. The following instructions will guide you through the installation from source.

Make sure you have [Docker](https://www.docker.com) and the [Poetry](https://python-poetry.org) package manager installed. Then clone the repository and use poetry to set up the project:
```sh
$ git clone https://github.com/digitalernachschub/staves.git
$ cd staves
$ poetry install
```

## Getting started
Staves images are defined declaratively using [TOML](https://toml.io/en/) markup. Store the following image specification in a file called `staves.toml`:
```toml
name = 'staves/bash'
packages = ['app-shells/bash']
command = ['/bin/bash', '-c']
```

This file tells Staves to bundle the Gentoo package "app-shells/bash" and its runtime dependencies into a container image tagged "staves/bash". The image's entrypoint is defined as "/bin/bash -c". Most likely, you are not running Gentoo as your host system. Therefore, Staves relies on a _builder image_. We can use any stage3 for that purpose, so let's pull one of the official Docker images:
```sh
$ docker pull gentoo/stage3-amd64-hardened-nomultilib
```

Now we are ready to start the build:
```sh
$ poetry run staves build --builder gentoo/stage3-amd64-hardened-nomultilib --build-cache staves
```
This will take some time. The command performs the following steps:
* Download the official Docker image of the latest package list (i.e. Portage snapshot)
* Create a binary package from every package in the builder. These binary packages are cached in the Docker volume `staves` to speed up subsequent builds.
* Install _app-shells/bash_ and its runtime dependencies into `/tmp/rootfs` of the build container
* Create the file `staves_root.tar` in your working directory from the contents of `/tmp/rootfs`
* Create and tag a Docker image with the contents of the tarball

Once the command is finished, we can test the newly created image:
```sh
$ docker run --rm staves/bash "echo Hello World!"
```

### Customizing the image
The previous example uses only the most basic `staves.toml`, but there are several ways to customize the resulting image.

#### Package-specific configuration
A Staves image specification can control individual feature toggles of a package. In Gentoo Linux, these are called _USE flags_. The `app-shells/bash` package, for example, can also be compiled without Native Language Support. We do this by specifying a TOML table with the package name as the identifier and the USE flags as an array:
```toml
['app-shells/bash']
use = ['-nls']
```
For one, this will shave off a couple of megabytes from the resulting image. For another, there are cases where disabling functionality will reduce the attack surface of the resulting image. See [packages.gentoo.org](https://packages.gentoo.org/) for installable packages and their USE flags.

#### Build environment customization
Staves allows adjusting the global build environment. For example, we can enable aggressive compiler optimizations via `CFLAGS` or enable support for the AVX instruction set:
```toml
[env]
CFLAGS="${CFLAGS} -O3"
CPU_FLAGS_X86="${CPU_FLAGS_X86} avx"
```
Values in the `env` section of a `staves.toml` will be appended to the [make.conf](https://wiki.gentoo.org/wiki//etc/portage/make.conf) of the builder and are applied to all packages. See the [make.conf.example](https://github.com/gentoo/portage/blob/master/cnf/make.conf.example) file for a documentation of allowed values.

However, it is also possible to apply package-specific configurations to the build environment. The _env_ table can have custom attributes that represent environment configurations themselves. These environments can be applied to individual packages using the _env_ attribute of a package configuration:
```toml
[env.nocache]
FEATURES="-buildpkg"

['=dev-utils/mylibrary-9999']
env = ['nocache']
```

Technically, the _env.nocache_ section will create the file `/etc/portage/env/nocache`. This environment is then applied to the specified package using a corresponding entry in `/etc/portage/package.env`.


## How to build images based on MUSL libc
Building images based on anything else than GLibc will require you to prepare a stage3 image with a corresponding toolchain. The official Gentoo docker images do not include a stage3 with a MUSL toolchain at the time of writing (2020-10-23), but there are several other ways to achieve this. For example, you can use [Catalyst](https://wiki.gentoo.org/wiki/Catalyst) or [GRS](https://wiki.gentoo.org/wiki/Project:RelEng_GRS) to bootstrap the corresponding system. This how-to will use the Docker image generator _[gentoo-docker-images](https://github.com/gentoo/gentoo-docker-images)_ to create a MUSL stage3 for amd64.

As a prerequisite, you need to have the [buildx](https://docs.docker.com/buildx/working-with-buildx/) Docker extension installed. If not, the following instructions will build and install the buildx command:
```sh
$ export DOCKER_BUILDKIT=1
$ docker build --platform=local -o . git://github.com/docker/buildx
$ mkdir -p ~/.docker/cli-plugins
$ mv buildx ~/.docker/cli-plugins/docker-buildx
```

Now we can clone the gentoo-docker-images repository and run _build.sh_ with the appropriate _TARGET_ environment.
```sh
$ git clone https://github.com/gentoo/gentoo-docker-images.git
$ cd gentoo-docker-images
$ TARGET=stage3-amd64-musl-hardened ./build.sh
```
This will create a docker image tagged as `gentoo/stage3:amd64-musl-hardened`. Since Staves works with any stage3, this image can simply be used as a builder to produce MUSL-based images.

## Comparison to other tools
OCI images are built around the idea of different layers that are merged together to create a container filesystem. This approach promotes reusability of layers and permits layer caching. The drawback is that the number of layers required for a single image adds up quickly. Since these layers typically come from different entities and organizations, you have to trust each of them to provide uncompromised images. If any of the layers are compromised, your final image will likely be compromised, too.

Staves does not rely on layering to provide the final image. Every image is built from scratch. You need to trust the Gentoo builder image and the packages you are installing. From there, everything is built from the sources. The security of this process is arguably easier to verify than the layering approach involving many different parties.

### Docker multistage builds
Multistage builds operate on the same principle as Staves in that both separate build-time and run-time dependencies. In multistage builds, the installation steps need to be invoked manually, but you are free to choose any build image or package manager to perform the steps. This results in an imperative image definition with several `RUN` steps. For multi-platform builds, these need to be parameterized with build arguments.

Staves is limited to Gentoo builders, but provides a declarative way to create images. The prerequisite is that there is a Gentoo ebuild for the installed packages. There is no need to parameterize for multiple platforms, because platform specific steps are performed in the ebuilds.

### buildkit, buildctl, img, buildx
Buildkit improves upon regular `docker build` invocations, because it can be executed without root privileges, has a pluggable frontend (i.e. "image format"), and a number of other goodies. Buildkit uses a library-first approach and is used by different command-line tools, such as _buildctl,_ _img_ and _buildx_.

Staves currently depends on Docker and defines a custom image format. Buildkit and its descendants compare similarly to Staves as as Docker multistage builds. They are more flexible, becase you can depend on other base images and choose any suitable builder as an image. Staves makes use of Gentoo's Portage package manager and therefore it relies on Gentoo infrastructure and depends on a Gentoo stage3 builder image.
