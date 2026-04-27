import os


def test_conftest_sets_dev_no_auth():
    assert os.environ.get("PROMPTPRESSURE_DEV_NO_AUTH") == "1"
