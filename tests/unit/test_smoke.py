import pytest

pytestmark = pytest.mark.unit


def test_packages_are_importable() -> None:
    import contracts  # noqa: F401
    import persistence  # noqa: F401
    import simulator  # noqa: F401
    import swimcore  # noqa: F401
    import swimtools  # noqa: F401
