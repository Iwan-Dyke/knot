# ADR 0044: Extend visual palettes and knowledge themes independently

- Status: Accepted
- Date: 2026-11-08
- Implementation: Implemented
- Extends: ADRs 0016, 0017 and 0026
- Subsequently extended by: [ADR 0045](0045-persistent-visual-themes-and-css-palettes.md) for saved preferences and CSS palettes

This record describes the original legacy-viewer integration. The same palette
contract now also styles the Graph/Library interface in
[ADR 0047](0047-unified-knowledge-library-and-graph-exploration.md), which is the
default `knot view` output. Topic export flags below apply to `knot view --legacy`;
the current interface exposes topic navigation and filters within the page.

## Context

An open-source installation needs to customise its viewer and its knowledge
categories without changing application code. Viewer colours and fonts were
embedded in Python and Matrix-specific CSS. Knowledge themes already belonged to
the dataset catalogue, but adding a category required editing that catalogue by hand.
The same word describes two independent concerns: appearance and topic navigation.

## Decision

Keep visual palettes as versioned JSON definitions in the presentation package or
an explicitly selected external file. Share named colour/font tokens between CSS
and canvas rendering. The layout stylesheet and graph semantics stay application
code. Matrix remains the default; Paper demonstrates a light palette. Missing
tokens inherit Matrix values. Bundled filenames supply theme names without a code
registry. The viewer exposes `--visual-theme`; existing `--theme` remains a topic
filter. `knot view` delegates to the existing exporter.

Validate palette fields before writing an export. Accept hexadecimal colours and
local font families, excluding executable extensions, arbitrary CSS and remote
assets. Export embeds the resolved values. Changing a palette changes neither
evidence nor membership, identity, review status, node roles or inference dashes.
Contrast remains the theme author's responsibility. Palette selection is per export;
this increment does not add a preference database or live browser theme switcher.

Expose `knot themes list`, `add` and `import` over the existing dataset catalogue.
Use the same definition validation for imports, note navigation and graph rebuilds.
Validate a whole import before atomically publishing the updated catalogue; preserve
unrelated catalogue fields. Identical retries do nothing. Conflicting IDs fail
instead of replacing definitions or implicitly refreshing review fingerprints.
Adding a category never creates ontology types or changes saved note revisions.
Existing explicit organisation rebuilds apply keyword suggestions and update
filters. Membership review remains independent from claim acceptance.

## Alternatives and consequences

A plugin loader would permit arbitrary layout and classification algorithms, but
introduce executable code and compatibility boundaries that these workflows do not
need. Declarative JSON fits the existing catalogue and offline export architecture.
It supports colour/font customisation rather than arbitrary new viewer behaviours.

A stylesheet alone cannot consistently style the canvas graph. One palette shared
by both rendering surfaces avoids separate user-facing colour configurations.
Keeping appearance separate from topic definitions lets a dataset use any palette
without changing the meaning or history of its knowledge categories.

## Verification

Synthetic tests cover external palettes, bundled discovery, default isolation,
invalid input without overwritten exports, page/canvas consistency, and unchanged
evidence and review state. Knowledge-theme tests cover add/import retries, atomic
conflict rejection, existing catalogue preservation, note selection and keyword
rebuilds. Optional browser checks exercise both Paper and an external palette on
desktop and mobile, with network requests blocked.
