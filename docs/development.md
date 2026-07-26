# Development

Development happens in the open through focused branches and pull requests to
`master`. Keep a change small, describe its intent, and include tests and
documentation when behaviour changes.

## Dependencies and locks

Edit `environment.yml` to change development tooling, then regenerate the
shared lockfile for all supported platforms:

```shell
conda-lock lock --micromamba --file environment.yml \
  --lockfile gleiswerk.conda-lock.yml \
  --platform osx-arm64 --platform osx-64 --platform linux-64 --platform win-64
```

Commit both files. The CI lockfile job verifies that they stay in sync.

## Releases

The release workflow is triggered by a pushed `v*` tag. A release tag must
match the version in `pyproject.toml`, for example `v0.0.1`. The workflow builds
and tests the Conda package, uploads it to the `micknudsen` Anaconda channel,
and creates the corresponding GitHub release.
