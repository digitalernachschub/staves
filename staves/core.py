from enum import auto, Enum


class Libc(Enum):
    glibc = auto()
    musl = auto()


class StavesError(Exception):
    pass
