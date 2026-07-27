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

Prepare every release in its own pull request before creating a tag. The
release-preparation pull request must:

1. Confirm that the release's planned work is complete.
2. Update the single authoritative version in `pyproject.toml`.
3. Add committed release notes at `docs/releases/vX.Y.Z.md`. They must describe
   new capability, relevant configuration contracts, and explicit non-goals.
4. Update any user-facing version references that would otherwise become
   stale.
5. Pass the complete local release gate:

   ```shell
   ruff format --check .
   ruff check .
   pyright
   python -m pytest
   mkdocs build --strict
   conda-build --override-channels --channel conda-forge conda-recipe
   ```

Use [the release-notes guide](releases/README.md) for the required format.
The release-preparation pull request must not create a tag, publish a package,
or create a GitHub release.

After the pull request is merged and the maintainer explicitly approves the
release, create the tag without manually entering its version:

```shell
python scripts/create_release_tag.py
```

The helper reads `pyproject.toml`, requires a clean `master` matching
`origin/master`, checks that the matching committed release notes exist, and
creates an annotated tag locally. Review the tag before triggering publication:

```shell
python scripts/create_release_tag.py --push
```

`--push` is an explicit opt-in: it verifies that the existing local tag targets
the current `master` commit, then pushes that same version-derived tag to
`origin` and starts the release workflow.

The pushed `vX.Y.Z` tag must match `pyproject.toml`, for example `v0.0.2`.
The release workflow builds and tests the Conda package, uploads it to the
`micknudsen` Anaconda channel, and creates the corresponding GitHub release
using the committed `docs/releases/vX.Y.Z.md` file as its release notes.
