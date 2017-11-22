FROM gentoo/portage as portage

FROM ameto/gentoo-stage3-amd64-musl-hardened

COPY --from=portage /usr/portage /usr/portage

ENV LANG en_US.UTF-8
ENV MAKEOPTS="-j9 -l8"
ENV EMERGE_DEFAULT_OPTS="--quiet"

RUN echo "dev-libs/openssl -bindist" >> /etc/portage/package.use
RUN echo "net-misc/openssh -bindist" >> /etc/portage/package.use
RUN emerge -1N openssh openssl

RUN echo "dev-vcs/git -gpg -perl" >> /etc/portage/package.accept_keywords
RUN emerge app-portage/layman
RUN layman -f
RUN layman -a musl

RUN echo "dev-lang/python:3.6" >> /etc/portage/package.accept_keywords
RUN emerge dev-lang/python:3.6
ENV PYTHON_TARGETS="python3_6"
RUN emerge -N @world --exclude gcc
RUN eselect python set --python3 python3.6
COPY create_rootfs.py create_rootfs.py
CMD ["python3.6", "create_rootfs.py"]