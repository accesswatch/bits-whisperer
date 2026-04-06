# Release Notes

This directory contains per-feature release notes in Markdown format.
Each file corresponds to a feature flag identifier and is displayed
to users in the **What's New** dialog when the feature is first
enabled or updated.

## File naming

Use the feature flag identifier as the filename:

```
docs/release_notes/<feature_name>.md
```

For example: `watch_folder.md`, `live_transcription.md`.

## Format

Each file is standard Markdown. The first `# Heading` is used as the
feature title in the dialog. Keep notes concise — they are shown in
a scrollable dialog.

## Version sections

Use `## Version X.Y.Z` headings to separate notes by version. The
application displays only the sections relevant to the user's
upgrade path.

## How it works

The `feature_flags.json` file references these notes via special
`bitswhisperer://release-notes/<feature_name>` URIs. At runtime the
application resolves them to raw GitHub URLs pointing at
`docs/release_notes/<feature_name>.md` to fetch the content.

## Adding release notes for a new feature

1. Create `docs/release_notes/<feature_name>.md`.
2. Add the `release_notes_url` field in `feature_flags.json`.
3. Commit both files together.
