# Staves
Staves is a container image builder based on the _[Portage](https://wiki.gentoo.org/wiki/Portage)_ package manager for Gentoo Linux. Staves leverages Gentoo's infrastructure to build highly customized images optimized for image size, speed, and security.

_Staves is in alpha status and is not recommended for production use_

## Features
* Minimal dependencies result in small image sizes and reduced attack surface
* [Feature toggles](https://wiki.gentoo.org/wiki/USE_flag) provide even more fine-grained control over image size and attack surface
* Full control over the build process (e.g. [compiler settings](https://wiki.gentoo.org/wiki/GCC_optimization) allows for images customized to a specific Platform or CPU
* Access to [hardened build toolchains](https://wiki.gentoo.org/wiki/Project:Hardened) with things like PIC (Position Independent Code) and SSP (Stack Smashing Protection)

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
For one, this will shave off a couple of megabytes from the resulting image. For another, there are cases where disabling functionality will reduce the attack surface of the resulting image.

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
