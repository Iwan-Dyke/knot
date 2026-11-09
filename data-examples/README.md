# Synthetic example knowledge

These invented notes are part of KNOT's MIT-licensed examples. They contain no
personal knowledge. The demo and browser tests use the same files.

Open the examples directly in one browser tab with Graph and Library buttons:

```sh
knot view example
```

This builds a fresh disposable dataset in the system temporary directory. The
printed HTML path stays available after the command finishes. It does not read or
change your normal dataset selection. Add `--no-open` to export without launching.
These inputs are included in installed packages as well as source checkouts.

To keep an example dataset in a folder of your choice from a source checkout:

```sh
just example-data /tmp/knot-example-data
./knot view --data-root /tmp/knot-example-data --output /tmp/knot-example.html
```

Pandoc and the viewer extra are needed to generate the HTML. The finished file
opens offline without Python or Pandoc. The generator refuses a nonempty destination
and does not select it as your normal dataset, commit, push or change personal data.

`knot view example` opens Focused mode on **Community garden project**, with its
connected notes and entities already visible. Ordinary `knot view` still starts
with search/selection. An explicit URL fragment or `--focus SEARCH` overrides the
demo's starting record.

The generated collection contains eight notes and six entities, with nine active
source-backed claims plus saved note links and associations. Markdown and Org,
overlapping themes, an isolated question, two curated notes with exact citations,
revised source text, an accepted claim and an unreviewed correction are included.
Review events are synthetic demonstration decisions, made only in this new dataset.

## Explore the connected example

1. Start at **Community garden project**. Its graph connects the proposed trial,
   water conservation, a tank dependency, volunteers and associated notes.
2. Use **+ Hop** to reveal the **Trial timing decision** and more note links. Use
   **Live layout** or **Node spacing** to spread the visible neighbourhood out.
3. Turn off **Associated notes** to inspect entity relationships such as `dependsOn`,
   `workedOn`, `madeDecision` and `decisionAbout`. Review filters still apply.
4. Open **Why the trial is still a proposal** in Library. Its synthesis cites the
   proposal, decision and readiness check; open the pinned sources to verify them.
5. Read **An independent question** for the deliberately isolated case. A single
   node is correct for that note; the other thirteen records form a connected graph.

The scenario distinguishes proposals and dependencies from completed work. It does
not claim the trial happened or water was saved. Multiple notes in this scenario
are not independent corroboration.

## Extend the fixtures

Edit the example inputs here to extend the shared demo; use the existing authoring
APIs in `knot.writing.examples` to generate authoritative records.
`scripts/example_data.py` delegates to that same generator for development use.
Include new input files in `pyproject.toml` so installed packages have the same demo.

Generated datasets and HTML belong outside this directory. Tests always generate
their own temporary copy.

For an explicitly generated dataset, run `just quality --data-root /tmp/knot-example-data`.
Source integrity checks pass. The current type audit reports five editorial
`untyped_endpoint` notices because it misses types held in native declarations;
the viewer does read those declarations. These notices remain a diagnostics limitation.
