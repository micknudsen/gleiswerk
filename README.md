# Gleiswerk

[![Conda Version](https://img.shields.io/conda/vn/micknudsen/gleiswerk?cacheSeconds=300)](https://anaconda.org/micknudsen/gleiswerk)
[![Conda Downloads](https://img.shields.io/conda/dn/micknudsen/gleiswerk?cacheSeconds=300)](https://anaconda.org/micknudsen/gleiswerk)

Gleiswerk is a local-first, configuration-driven model railway control and
automation system. It is being designed around a Märklin H0 reference layout
while keeping its automation core independent of any particular command
station.

Version 0.0.2 introduces validated, versioned layout configuration. It remains
descriptive only: Gleiswerk does not yet control railway hardware or automate
train movements.

## Command-line interface

After installing the project in a development environment:

```console
gleiswerk --help
gleiswerk --version
gleiswerk layout validate layout.toml
```

The package can also be invoked as a Python module:

```console
python -m gleiswerk --help
```

## Development

Gleiswerk requires Python 3.11 or newer. The core, command-line interface, and
simulator target macOS, Linux, and Windows.

Create the Conda development environment and install the local checkout:

```console
conda env create --file environment.yml
conda activate gleiswerk-dev
python -m pip install --no-deps --no-build-isolation --editable .
python -m pytest
```

Run the complete local quality suite with:

```console
ruff format --check .
ruff check .
pyright
python -m pytest
mkdocs build --strict
```

`environment.yml` declares the development toolchain. Its resolved,
multi-platform counterpart, `gleiswerk.conda-lock.yml`, is committed for
reproducible environments. Update it after changing `environment.yml`:

```console
conda-lock lock --micromamba --file environment.yml --lockfile gleiswerk.conda-lock.yml \
  --platform osx-arm64 --platform osx-64 --platform linux-64 --platform win-64
```

## Building the Conda package

The Conda recipe reads the package version from `pyproject.toml`; do not add a
second version value to the recipe. Build and test the package locally with:

```console
conda-build --override-channels --channel conda-forge conda-recipe
```

The recipe builds one platform-independent `noarch: python` artifact. It
installs that artifact in a fresh test environment and verifies the package
import plus `gleiswerk --help` and `gleiswerk --version`.

Gleiswerk releases are distributed through the `micknudsen` Conda channel.
The project will not be published to PyPI.

## Project decisions

Important technical and project decisions are recorded in
[`docs/adr`](docs/adr). The documentation site provides a concise
[getting-started guide](docs/getting-started.md) and the evolving architecture.

## License

Gleiswerk is available under the MIT License.
