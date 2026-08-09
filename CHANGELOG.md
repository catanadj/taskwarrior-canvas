# Changelog

Notable changes to Kyanbasu are documented here. The project follows semantic
versioning from the `0.2.0` release onward.

## [Unreleased]

### Added

- Guided decision maps with factor, option, and outcome notes; contextual branch
  creation; a decision review checklist; choice rationale; and immutable,
  exportable commitment snapshots that preserve alternative branches.
- An inversion analysis pass for decisions and options, including failure-mode
  factors, early-warning review, safeguard actions, and completeness feedback.
- A branching first-, second-, and third-order consequence pass for options,
  with order-aware prompts, parallel outcomes, and incomplete-branch feedback.
- A documented personal decision method based on target, states, acts,
  uncertainty, precommitment, and outcome-independent review.

### Changed

- The implementation now lives entirely in the `kyanbasu` Python package.
- The Python distribution is named `kyanbasu` and generated workspaces are
  written to `Kyanbasu.html`.
- TaskCanvas notes and workbench JSON exports remain importable and are
  normalized to Kyanbasu formats on the next export.

### Removed

- The TaskCanvas command, wrapper, package, environment variables, browser API
  aliases, storage migration, and background aliases.

## [0.2.0] - 2026-07-16

### Added

- The Kyanbasu command, Python module, source wrapper, visual identity, and
  runtime API names.
- A thinking canvas with mind-map notes, note identifiers, buckets, editable
  outliner views, search, focus tools, colours, multi-selection, and JSON
  import/export.
- Multiple workbenches with duplication, switching, rename protection, and
  workspace-level import/export.
- Annotated note relationships with selection, editing, drag-to-link, and
  relationship discovery tools.
- Canvas navigation, minimap, selection inspector, undo/redo, and compact map
  organization.
- A command review workflow with editable and removable staged commands.

### Changed

- Runtime storage, downloads, and public browser APIs now prefer `kyanbasu`
  names while migrating and synchronizing legacy TaskCanvas state.
- Dependency links use static direction cues instead of continuous animation,
  substantially reducing idle browser CPU usage.
- Task, project, note, bucket, toolbar, and workspace interactions received a
  broad usability and placement pass.
- Package metadata and release checks now describe and validate Kyanbasu.

### Compatibility

- The `taskcanvas` console command, `python -m taskcanvas`, `TaskCanvas.py`,
  `taskcanvas` Python package, and `TaskCanvas.html` output remain supported.
- The Python distribution and GitHub repository retain the
  `taskwarrior-canvas` identifier during the compatibility period.
- Legacy browser storage and TaskCanvas note/workbench exports remain readable.

[Unreleased]: https://github.com/catanadj/kyanbasu/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/catanadj/kyanbasu/releases/tag/v0.2.0
