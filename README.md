Staves is a container image builder based on the _[Portage](https://wiki.gentoo.org/wiki/Portage)_ package manager for Gentoo Linux. Staves leverages Gentoo's infrastructure to build highly customized images optimized for image size, speed, and security.

_Staves is in alpha status and is not recommended for production use_

# Features
* Minimal dependencies result in small image sizes and reduced attack surface
* [Feature toggles](https://wiki.gentoo.org/wiki/USE_flag) provide even more fine-grained control over image size and attack surface
* Full control over the build process (e.g. [compiler settings](https://wiki.gentoo.org/wiki/GCC_optimization) allows for images customized to a specific Platform or CPU
* Access to [hardened build toolchains](https://wiki.gentoo.org/wiki/Project:Hardened) with things like PIC (Position Independent Code) and SSP (Stack Smashing Protection)

# Installation
Staves is not available via PyPI at the moment. The following instructions will guide you through the installation from source.

Make sure you have [Docker](https://www.docker.com) and the [Poetry](https://python-poetry.org) package manager installed. Then clone the repository and use poetry to set up the project:
```sh
$ git clone https://github.com/digitalernachschub/staves.git
$ cd staves
$ poetry install
```

# Getting started
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
