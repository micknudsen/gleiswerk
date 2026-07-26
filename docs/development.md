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

The `Update Conda lockfile` workflow refreshes the resolved dependencies every
Monday at 06:20 UTC and can also be started manually from the Actions tab. It
creates or updates one `chore/conda-lock-update` pull request, so review and CI
always see the complete lockfile change.

For that pull request to trigger the normal `pull_request` checks, configure a
repository secret named `DEPENDENCY_UPDATE_TOKEN` with a fine-grained personal
access token (or GitHub App token) that has `contents: write` and
`pull-requests: write` permissions for this repository. The default
`GITHUB_TOKEN` cannot trigger those checks for a pull request it creates.

## Releases

The release workflow is triggered by a pushed `v*` tag. A release tag must
match the version in `pyproject.toml`, for example `v0.0.1`. The workflow builds
and tests the Conda package, uploads it to the `micknudsen` Anaconda channel,
and creates the corresponding GitHub release.
