# Gleiswerk

Gleiswerk is a local-first, configuration-driven model railway control and
automation system. It is being designed around a Märklin H0 reference layout
while keeping its automation core independent of any particular command
station.

The project is in its initial foundation phase. The first release proves the
packaging and delivery path before railway automation is introduced.

## Command-line interface

After installing the project in a development environment:

```console
gleiswerk --help
gleiswerk --version
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

Gleiswerk releases are distributed through the `micknudsen` Conda channel.
The project will not be published to PyPI.

## Project decisions

Important technical and project decisions are recorded in
[`docs/adr`](docs/adr).

## License

Gleiswerk is available under the MIT License.
