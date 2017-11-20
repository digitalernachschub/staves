FROM gentoo/portage as portage

FROM gentoo/stage3-amd64-nomultilib

COPY --from=portage /usr/portage /usr/portage

ENV MAKEOPTS="-j9 -l8"
ENV EMERGE_DEFAULT_OPTS="--quiet"
ENV ACCEPT_KEYWORDS="~amd64"
ENV USE="-bindist"
RUN emerge -N openssh openssl

RUN emerge dev-lang/python:3.6
ENV PYTHON_TARGETS="python3_6"
RUN emerge -N @world --exclude gcc
RUN eselect python set --python3 python3.6
COPY create_rootfs.py create_rootfs.py
CMD ["python3.6", "create_rootfs.py"]