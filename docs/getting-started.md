# Getting started

Gleiswerk currently provides a small command-line package. The supported
development environment is Conda using packages from conda-forge.

```shell
python scripts/update_dev_environment.py
```

The script creates `gleiswerk-dev` if it does not exist, updates it from the
checked-in multi-platform lockfile, and installs the current checkout in
editable mode. It works whether the environment is active or not. Activate the
environment afterwards when you want to work in it:

```shell
conda activate gleiswerk-dev
gleiswerk --version
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
