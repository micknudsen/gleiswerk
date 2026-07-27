# Gleiswerk agent instructions

## Change control

- Do not create, edit, delete, commit, push, tag, publish, or alter GitHub
  settings unless the user explicitly requests that action.
- Never commit changes unless the user explicitly asks to commit in the current
  conversation. Leave changes uncommitted for review and local testing first.
- Open pull requests ready for review by default. Create a draft only when the
  user explicitly requests a draft or the work is genuinely incomplete and
  must be shared before it is ready for review.
- Before proposing or implementing a substantial change, keep scope narrow and
  explain the intended outcome and verification.
- Preserve unrelated user changes in the worktree.

## Development style

- Prefer small, focused changes. One pull request should represent one coherent
  concern: a safety rule, bug fix, schema addition, simulator behavior,
  documentation change, or adapter increment.
- Design the automation core to be controller- and UI-independent. Hardware
  adapters, the simulator, CLI, Textual, and future web interfaces must not
  contain core safety logic.
- Treat safety invariants as explicit, testable rules, not UI conventions.
- Prefer local-first, configuration-driven, explainable behavior.
- Keep the simulator able to exercise the same core model as real hardware.
- Do not add unrestricted embedded scripting without explicit approval.
- Record significant, durable technical decisions as ADRs with context,
  decision, alternatives, and consequences.
- Use American English in source comments, documentation, and user-facing text.

## Testing and documentation

- Add or update tests when changing behavior.
- Run relevant formatting, linting, typing, tests, package, and documentation
  checks before asking for review.
- Documentation is documentation-as-code: keep it in Markdown, validate it
  with strict MkDocs builds, and keep examples executable or validated where
  practical.
- Keep the README a concise front door; put detailed guidance in `docs/`.

## Packaging and CI

- Distribute only through Conda in the `micknudsen` channel. Never publish to
  PyPI unless the user explicitly changes this policy.
- Keep one authoritative dependency declaration and regenerate the committed
  multi-platform Conda lockfile whenever it changes.
- Support macOS, Linux, and Windows in the development and CI toolchain.
- Pin third-party GitHub Actions to immutable commit SHAs with readable version
  comments. Do not enable automatic dependency-update merging.
- Releases are triggered only by pushed `vX.Y.Z` tags, and the tag must match
  the version in `pyproject.toml`.

## Repository governance

- `master` is the default branch. Treat it as PR-only; do not push directly.
- Use conventional-style commit titles when the user requests a commit.
- When a pull request fully resolves an issue, include a GitHub closing keyword
  such as `Closes #123` in the PR description so GitHub closes the issue when
  the PR is merged.
- Do not weaken branch protection, required checks, or release-environment
  protections without explicit user approval.
- GitHub CLI commands requiring the authenticated macOS Keychain must run with
  sandbox escalation (`require_escalated`). The sandboxed environment cannot
  access the Keychain and may incorrectly report the active `gh` token as
  invalid. Verify with an escalated `gh auth status` before requesting
  reauthentication.
