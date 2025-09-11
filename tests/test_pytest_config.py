import os


def test_timeout_config(pytestconfig):
    """Ensure each test has a 5 second timeout to prevent hangs."""
    # The timeout plugin should enforce a 5 second limit per test.
    assert pytestconfig.getoption("timeout") == 5


def test_parallel_execution(pytestconfig):
    """Ensure tests run in parallel to speed up the suite."""
    # xdist sets this environment variable on each worker process to the
    # total number of workers, so a value greater than 1 implies parallelism.
    worker_count = os.environ.get("PYTEST_XDIST_WORKER_COUNT")
    assert worker_count is not None and int(worker_count) > 1
