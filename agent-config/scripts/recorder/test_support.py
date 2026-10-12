"""One test-only door for artificial size stress documents."""
from read import _seal


def folded_for_test(document):
    return _seal(document)
