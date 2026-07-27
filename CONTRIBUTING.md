# Contributing to Gleiswerk

Thanks for helping build Gleiswerk. The repository is public and contributions
are welcome through focused pull requests.

## Set up the project

Follow the [getting-started guide](docs/getting-started.md). Use the locked
environment when you need the exact dependency set used in CI.

## Make a change

1. Create a branch from current `master`.
2. Keep the change focused and document user-visible or safety-relevant
   behavior.
3. Run formatting, linting, type checks, tests, and `mkdocs build --strict`.
4. Open a pull request using the provided template.

`master` is intended to be protected: changes are reviewed through pull
requests, merged with squash commits, and branches are deleted after merge.

## Dependency changes

When changing `environment.yml`, regenerate and commit
`gleiswerk.conda-lock.yml` for macOS, Linux, and Windows. See
[Development](docs/development.md#dependencies-and-locks) for the command.

## Reporting problems

Use the issue templates for bugs and feature proposals. Please do not report
security-sensitive issues publicly; follow [SECURITY.md](SECURITY.md) instead.
