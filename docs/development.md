# Development

Development happens in the open through focused branches and pull requests to
`master`. Keep a change small, describe its intent, and include tests and
documentation when behavior changes.

## Dependencies and locks

Edit `environment.yml` to change development tooling, then regenerate the
shared lockfile for all supported platforms:

```shell
python scripts/update_conda_lockfile.py
```

The script runs `conda-lock` from `gleiswerk-dev` and updates
`gleiswerk.conda-lock.yml` for macOS (Apple Silicon and Intel), Linux, and
Windows. It does not change `environment.yml`; review and commit only the
generated lockfile when its dependency updates are acceptable. The CI lockfile
job verifies that the lockfile's input matches `environment.yml`; it does not
require newly published compatible packages to be locked immediately.

To create or refresh the local development environment from the committed lock
file, run this from the repository root:

```shell
python scripts/update_dev_environment.py
```

It works whether `gleiswerk-dev` already exists or is active. The first run
bootstraps it from `environment.yml`; every run then reconciles it with
`gleiswerk.conda-lock.yml` and installs the checkout editable with pip
dependency installation disabled.

## Releases

The release workflow is triggered by a pushed `v*` tag. A release tag must
match the version in `pyproject.toml`, for example `v0.0.2`. The workflow builds
and tests the Conda package, uploads it to the `micknudsen` Anaconda channel,
and creates the corresponding GitHub release.
