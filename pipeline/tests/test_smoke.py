import lutece_pipeline


def test_package_is_importable() -> None:
    assert callable(lutece_pipeline.main)
