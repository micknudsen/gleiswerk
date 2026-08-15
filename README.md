# Gleiswerk

[![Conda Version](https://img.shields.io/conda/vn/micknudsen/gleiswerk?cacheSeconds=300&style=for-the-badge)](https://anaconda.org/micknudsen/gleiswerk)
[![Conda Downloads](https://img.shields.io/conda/dn/micknudsen/gleiswerk?cacheSeconds=300&style=for-the-badge)](https://anaconda.org/micknudsen/gleiswerk)

Gleiswerk is a local-first, configuration-driven model railway control and
automation system. It is being designed around a Märklin H0 reference layout
while keeping its automation core independent of any particular command
station.

Schema version 3 provides validated, resource-complete logical topology,
compiled route plans, explainable static compatibility analysis, bounded
in-memory reservation evaluation, and evidence-gated movement-authority
decisions. The authority workflow is controller-independent and local only: it
does not control railway hardware or authorize a real train to move.

See the [layout configuration guide](docs/layout-configuration.md) for the
schema-v3 authoring model and validated reference layouts.

## Command-line interface

After installing the project in a development environment:

```console
gleiswerk --help
gleiswerk --version
gleiswerk layout validate layout.yaml
gleiswerk layout compatibility layout.yaml
gleiswerk layout reservations layout.yaml operations.yaml
gleiswerk commissioning verify layout.yaml installation-binding.yaml \
  cs3-capture.yaml occupancy-expectations.yaml --live-hardware
```

The `layout reservations` workflow can evaluate reservations, logical
evidence, and bounded movement authorities from one finite YAML operations
document. See the [reservation and movement-authority CLI workflow]
(docs/reservation-cli-workflow.md) and [movement-authority contract]
(docs/movement-authority-contract.md) for its evidence requirements and
explicit safety boundary.

The opt-in [hardware commissioning workflow](docs/commissioning-cli-workflow.md)
checks a supervised, read-only CS3+ and S88 capture against a revision-matched
Installation Binding. It does not command hardware or grant permission for a
real train to move.

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
