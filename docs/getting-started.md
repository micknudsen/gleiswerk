# Getting started

Gleiswerk currently provides a small command-line package. The supported
development environment is Conda using packages from conda-forge.

```shell
conda env create --file environment.yml
conda activate gleiswerk-dev
python -m pip install --no-deps --no-build-isolation --editable .
gleiswerk --version
```

To use the exact resolved development dependencies, create the environment
from the checked-in multi-platform lockfile instead:

```shell
conda-lock install --name gleiswerk-dev gleiswerk.conda-lock.yml
conda activate gleiswerk-dev
python -m pip install --no-deps --no-build-isolation --editable .
```

Run the complete local quality suite before opening a pull request:

```shell
ruff format --check .
ruff check .
pyright
python -m pytest
mkdocs build --strict
```

The package recipe can be built locally with:

```shell
conda-build --override-channels --channel conda-forge conda-recipe
```
