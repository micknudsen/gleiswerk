# Release notes

Each released version has committed notes at `docs/releases/vX.Y.Z.md`. These
notes are the reviewable record of what a release adds and, just as importantly,
what it does not add. The release workflow uses the same file as the GitHub
Release body.

## Required format

Use these sections in order:

```markdown
# Gleiswerk vX.Y.Z

## New capability

State the user-visible capability added or changed.

## Configuration contract

Describe new or changed configuration vocabulary, validation, compatibility,
and a link to the complete contract. If no configuration contract changes,
say so explicitly.

## Non-goals

List the operational, safety, controller, simulator, or hardware behaviors
that remain outside this release's scope.
```

Keep the notes concise and user-facing. Do not describe internal implementation
details unless they affect a user's configuration or workflow. Use absolute
links to the published documentation so links work both on the documentation
site and in the GitHub Release.

## Release-preparation checklist

1. Confirm the planned release work is complete.
2. Update `pyproject.toml`, the only authoritative package-version value.
3. Create and commit the release-notes file using the required format.
4. Update stale user-facing version references.
5. Run the full local release gate documented in
   [Development](../development.md#releases).
6. Open and merge a dedicated release-preparation pull request.
7. Obtain explicit maintainer approval before creating and pushing the matching
   `vX.Y.Z` tag.

Use `python scripts/create_release_tag.py` to create the annotated local tag
from `pyproject.toml`. Run it again with `--push` only after reviewing the tag
and approving publication.

Steps 1–6 prepare a release only. They must not tag, publish, or create a
GitHub release.
