# ADR 0045: Save visual preferences and discover CSS palettes

- Status: Accepted
- Date: 2026-11-08
- Implementation: Implemented
- Extends: ADR 0044; replaces its per-export-only visual selection and JSON-only palette format

## Context

Users need a command to change the default appearance and a folder for their own
themes. A CSS file is familiar, but the graph canvas also needs concrete colour
and font values. A page-only stylesheet would leave the graph on another palette.

## Decision

Add `knot theme list`, `show`, `use` and `create`. Save `visual_theme` alongside the
existing dataset selection in user configuration. The dataset path becomes optional
in that file so appearance can be selected before dataset setup. Data commands still
require a dataset. Explicit `--visual-theme` overrides the saved choice for one export;
Matrix remains the initial default. Existing HTML snapshots are not changed in place.

Discover user palettes in a `themes/` folder beside the configuration file. Accept
CSS and JSON by slug filename or explicit path. Persist external paths as absolute
paths. Bundled names are reserved; CSS wins over JSON for a duplicate user filename.
`create` copies a complete palette to a new CSS file without overwriting or selecting
it. Include Paper and Midnight as the two alternatives to Matrix.

CSS palettes use one `:root` block with the existing named colour/font variables
and optional `color-scheme`. Parse those values through the existing palette validator
and render both the page and canvas from the result. Preserve JSON compatibility.
Validation occurs before saving a preference or replacing an export. Missing selected
files fail explicitly instead of silently changing appearance.

## Alternatives and consequences

Arbitrary CSS would support layout changes, imports and selectors but would require
a browser-driven canvas bridge and a broader extension contract. A constrained CSS
palette keeps one set of values, offline exports and the current graph semantics.
Users can edit colours and local font families; new layouts remain application code.

Separate appearance configuration would avoid extending the existing settings file
but add another profile boundary. Optional fields let dataset selection preserve
appearance and let the existing configuration-path override isolate tests and profiles.

## Verification

Synthetic tests cover selection before dataset setup, persistence across dataset
changes and working directories, one-export overrides, CSS discovery, named lookup
precedence, safe template creation, invalid CSS and preservation of existing settings.
Browser checks cover Paper, Midnight and custom CSS/JSON on desktop and mobile,
including matching page/canvas colours, unchanged evidence and offline resources.
