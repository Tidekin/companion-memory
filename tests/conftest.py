from pathlib import Path


def pytest_configure(config):
    # pytest creates basetemp itself, but expects its parent to exist in a fresh checkout.
    if config.option.basetemp:
        Path(config.option.basetemp).parent.mkdir(parents=True, exist_ok=True)
