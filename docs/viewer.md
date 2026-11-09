# Browse the Library and explore the graph

Run commands from the repository root after [setup](../README.md#installation).
Examples use the selected dataset; see
[dataset selection](datasets.md#select-a-dataset) for external folders. Replace
uppercase identifiers with values returned by your own dataset.

## Graph and Library snapshot

Install Pandoc separately and the `visualisation` (or `dev`) extra, then run:

```sh
knot view
just visualise
knot view example
knot view --data-root /path/to/dataset --output /tmp/knowledge.html --visual-theme paper
```

`knot view` and `just visualise` generate and open one browser tab containing all three
views. The **Library**, **Graph** and **Idle** buttons switch within that tab. Use `--no-open`
to generate without launching a browser. `knot browse` and `just browse` retain
export-only defaults, with `--open` available explicitly.

The default output is `views/library.html`
under the selected dataset. The interface opens in **Graph**.
For an ordinary dataset, no network is constructed until you select a record or
choose **Live network**. The synthetic demo starts on its connected garden project.
**Library** opens the same
selection in a three-panel reading view. An explicit Library URL fragment opens the
reader directly. Browser Back/Forward restores selection, filters, branches and view
state within the session.

`knot view example` builds a fresh synthetic dataset in the system temporary
directory, ignoring the selected dataset without changing its configuration.
Its generated HTML stays there after the command exits so the browser can read it;
the printed path identifies the disposable folder. The example inputs are bundled
with package installations too. An explicit `--data-root` cannot be combined with
`example`. Use `--focus "Example project"` or `just visualise "Example project"`
to prefill search; this does not exclude records from the export.
An explicit `--focus` also replaces the demo's automatic starting selection with
search. The [example tour](../data-examples/README.md#explore-the-connected-example)
shows dependencies, decisions, note links, evidence and the deliberately isolated note.

The default viewer accepts `--data-root`, `--output`, `--visual-theme`, `--focus`,
`--open` and `--no-open`, plus the optional example/search argument. Use the page's
filters for review status, origin, kind, type and topic. Export-time `--graph`,
`--accepted-only`, `--theme`, `--kind`, `--no-themes` and `--frameworks` belong to
`knot view --legacy`; they are not options on the Graph/Library exporter.

## Read in Library

The Library includes standalone and unclassified notes, overlapping theme groups,
entity-type groups, recently created/modified notes and title/alias/body search.
Groups are virtual navigation paths. One note keeps one identity even when several
themes include it. Recently viewed items stay in memory and reset on reload/close;
KNOT writes no browsing history to the dataset or browser storage. The browser may
retain its own URL history.

Markdown and Org are rendered through sandboxed Pandoc (tested with 3.1.3) and a
restricted HTML allowlist. Use **Exact source** for the preserved text; unsupported
conversion falls back to source display. External images, executable/raw HTML and
arbitrary file links are not loaded. Web links open only when deliberately selected.
No Pandoc code is included in the resulting HTML.

Current note bodies and older bodies needed by citations are included. The revision
timeline shows other committed versions as **not included**, with all history still
preserved in the dataset. Pinned source navigation never silently substitutes a
newer revision. Context separates author-declared links from claims, shows original
and curated authorship, and retains review, origin, lifecycle and correction history.
Binary originals are not embedded; extracted/transcribed source text is labelled.

Select a result or navigation entry to read it. **Formatted** and **Exact source**
switch between rendered and preserved text; **A− / A+** adjust reading size.
The context panel provides outgoing links, backlinks, related entities, source-backed
claims and historical corrections. Expand a claim or citation for its evidence;
**Open pinned source** reads that exact included revision. An entity's reader lists
its associated notes and literal attributes. **Explore connections** switches to a
focused graph of the same canonical record; **Read in Library** returns to reading.
Browser editing and review actions are not implemented; use the CLI or authorised
MCP authoring workflows.

## Focused and live graph exploration

Graph exploration starts with one hop. Use hop controls, individual Expand/Collapse
buttons, or Focus to change the centre. The keyboard-accessible Connections list
provides the same navigation without using the canvas. Shared neighbours survive
when another branch still reaches them. **Focused** starts with a static layout.
Choose **Live layout** to let the visible neighbourhood rearrange itself, then
**Pause layout** to keep the resulting positions. Expanding branches and changing
filters respect that choice; enabling motion does not load the full network.
The shared **Node spacing** slider adjusts the distance between moving nodes. While
paused, it spreads or draws together existing positions around the centre without
changing zoom or starting animation, retaining manual placement. The percentage
applies to both modes and is retained when switching views within the page session.
Use **Fit** to see the arrangement, then zoom to read crowded areas; a dense graph
can still contain overlapping labels and edges.
Cross-links can be hidden explicitly. A focused graph is capped at 100 records and
300 connections, with counts and paged selection for omitted neighbours.

Choose **Live network** for the full network with moving nodes, live relationship
filters and spacing controls. Use **Pause layout** to inspect it without motion and
**Resume layout** to rearrange it again. Opening Library or hiding the browser tab
pauses simulation; returning resumes only if you left motion enabled. Reduced-motion
preferences start Live network paused; Focused starts paused in a new page session.
An explicit request can enable motion in either mode. Switching modes retains their separate
motion settings, positions and camera state; Focused centres a newly selected record
when needed.
Both modes use one graph instance, canonical selection and the same Library page.
Live network requires confirmation above 100 records and can be slower; it is outside
the bounded focused-graph performance target. “Live” describes the layout and filters,
not automatic updates from files.

Notes use boxes labelled Note; entities use circles with their types in the label.
Arrows show direction; dashed navigation links and inferred claims remain distinct
from explicit claims. In the default Matrix palette, accepted claims are bright
green, unreviewed claims muted green and saved navigation blue. Inspect the selected
record's context for exact status, relationship meaning and evidence. Canvas edges
do not establish acceptance or identity equivalence.

**Associated notes** is available in both graph modes. Unchecking it hides
associated/standalone note nodes and note-navigation
links. Entities and notes participating in visible claims (including literal
attributes) remain governed by the relationship filters. A note explicitly selected
as the focused root also stays visible. This changes graph visibility only: all
included notes remain searchable and readable in Library, with their evidence and
backlinks intact. The choice persists across view switches and navigation history
within the page session.

Accepted-only suppresses note navigation and disables the toggle, while retaining
the selected root and the Library's source notes.

The **Relationship filters** panel selects review status, origin, knowledge kind,
theme and node type. Search and Library collections help find records independently
of graph visibility. **Reset branches** resets focused expansion and placement;
it does not clear relationship filters or the spacing/motion choice. To restore
filtered connections, clear the relevant controls explicitly.

## Idle Mode

Choose **Idle**, then **Start**, for a cinematic tour of the current snapshot.
The nearly black canvas uses fine emerald connections and softly glowing nodes.
It starts from your selection when eligible, otherwise chooses a suitable starting
point. It needs no AI service or internet connection and never changes knowledge.

A node brightens and remains the focus for **10 seconds**. Its existing curated or
authored excerpt then fades into a reading panel for **10 seconds**, with attribution
and qualifications. After the panel fades away, the camera follows a real connecting
edge over **24 seconds**. Neighbours around the destination gradually appear while
old peripheral nodes fade. Fades are additional to the reading and travel periods.
Nodes without suitable text skip the reading stage and remain part of the journey.

The tour follows saved links, declared associations and eligible claims in either
direction, preserving original arrows and review/origin labels. At a fork it chooses
one branch. It continues until the path ends or would revisit a node in that chain,
then fades into another starting point without drawing a fictional connection.
There is no fixed step limit. Small collections pause longer before repeating;
a singleton completes its focus/reading sequence and then stays still.

Positions persist throughout the Idle session, including revisits. The camera moves
at a fixed zoom without force simulations or fitting the whole graph. A settled
neighbourhood contains at most 20 records/40 connections; the union during travel
contains at most 40/80. Omission counts describe capped context. Some geography can
remain offscreen, and long labels or dense cross-links can still overlap.

- **Start / Pause / Resume:** control the tour explicitly. Pause freezes the current
  camera position and fades; Resume continues from that point. Mouse movement does
  not stop it. Space also toggles playback outside interactive controls.
- **Depth:** choose one hop (default) or two.
- **Focus / Read / Travel:** choose the observation time, reading time and camera
  travel duration separately. Focus can be as short as 3 seconds; Read includes a
  15-second option. Changes apply when that phase next starts.
- **Exploration filters:** start with your Graph filters. Changes here affect only
  Idle and restart its focus sequence. Accepted-only hides authored navigation; it
  does not mark source notes as accepted claims.
- **Pause and read source:** available in the knowledge panel, opens the exact
  displayed revision in Library. Focusing the panel also pauses the tour.
- **Open another window:** open the same snapshot with the current Idle filters and
  press Start there. Move it to your second monitor, then choose **Full screen**.
  A browser may open a detachable tab. Each window loads its own copy of the snapshot.
- **Exit Idle:** restore the previous selection, reading revision, filters, layout,
  scroll and navigation context. Browser Back does the same; Forward opens Idle ready.
  Escape leaves full screen first, then exits Idle outside full screen.

A visible window keeps exploring while you work elsewhere. Hidden/minimised windows
freeze the sequence and resume its remaining time if you left it running. Reduced
motion retains focus and reading but replaces travel and fades with discrete updates.
Automatic visits do not add history, Library recents or dataset records. Full-screen
denial leaves the ordinary window usable; keeping the operating system awake is
outside this feature. Coordinates are released on Exit; a new session can have a
different geography.

Idle uses the loaded snapshot until you regenerate and reload it. Full screen and
filters do not redact embedded knowledge or add access controls. Run `knot view`
again after updating the application to generate a page with the current Idle controls.

## Snapshot freshness and troubleshooting

Regenerate and reload after changing knowledge. The displayed timestamp identifies
the snapshot; it cannot detect later edits. Export checks input signatures before
and after reading and atomically replaces the HTML only when verification succeeds.
This is an owner-local export containing all included data. Browser filters are not
access controls, and this command does not implement an MCP-scoped export.

The [example collection](../data-examples/README.md) supplies the shared demo/test
inputs. Generate it in an empty directory without changing your selected dataset:

```sh
just example-data /tmp/knot-example-data
knot browse --data-root /tmp/knot-example-data --output /tmp/knot-example.html --open
```

| Symptom | Check |
| --- | --- |
| New note or correction is missing | Rerun `knot view`, check the printed dataset/output path and select the record. An already open snapshot does not refresh itself. Use `--no-open` and reload if you want to reuse a tab. |
| A note is readable in Library but absent from the graph | Check Associated notes, relationship filters, the selected root, hop depth and omission counts. Use the Connections list to include an omitted neighbour. |
| Browser reports `ERR_FILE_NOT_FOUND` | Open the exact path printed by the latest export. Regenerate if the file or temporary example directory was removed; use `--output` for a stable location. |
| Export succeeds but browser launch fails | Open the printed HTML path manually. WSL uses `wslpath` and Windows PowerShell when available; a Windows browser needs the Windows/WSL path rather than a Linux-only file URL. |
| Pandoc or PyVis is missing | Install Pandoc separately and the `visualisation`/`dev` extra in KNOT's Python environment. The legacy literal-text viewer needs PyVis but does not require Pandoc. |

Run `knot view --help` or `knot view --legacy --help` for the respective options.

## Visual themes

Choose a theme and regenerate the viewer:

```sh
knot theme list
knot theme use midnight
knot theme show
knot view --open
```

Use `./knot` from an uninstalled source checkout. Three palettes are included:

| Name | Appearance |
| --- | --- |
| `matrix` | Green terminal colours; the initial default |
| `paper` | Light background with blue accents |
| `midnight` | Dark navy background with blue and teal accents |

`knot theme use` saves the choice in user configuration. `knot browse`, `knot view`, `just visualise`
and the Python viewer command use it for subsequent exports. It can be chosen
before setting up a dataset and remains selected when switching datasets. Existing
HTML files stay as exported; run `knot view --open` to generate an updated snapshot.

For one export, use `knot view --visual-theme paper` or pass a CSS/JSON path. This
overrides the saved preference without changing it. `--theme concepts` on
`knot view --legacy` filters knowledge by topic and can be combined with any visual
theme. In the current interface, use Library theme groups or Graph's theme filter
after exporting.

### Make or drop in a CSS theme

```sh
knot theme create ocean --from midnight
# Edit the CSS file at the reported path.
knot theme use ocean
knot view --open
```

`create` copies the complete palette, ready to edit. It never overwrites an existing
theme or selects it automatically. Drop your own `ocean.css` into the user theme
folder to make it available by name without changing application code. A minimal
example is:

```css
:root {
  color-scheme: dark;
  --accent: #60c7ff;
  --background: #061520;
  --text: #d8edfa;
  --entity: #247a99;
  --accepted: #60c7ff;
  --font-ui: system-ui, sans-serif;
  --font-graph: sans-serif;
}
```

The folder is normally `~/.config/knot/themes/`, or `$XDG_CONFIG_HOME/knot/themes/`.
With `KNOT_CONFIG`, it is the `themes/` folder beside that configuration file.
`knot theme list` reports its absolute path and the available names. Use lowercase
slug filenames. Bundled names are reserved; select an explicit file path to use a
custom file with the same name. If a custom name has both `.css` and `.json` files,
CSS takes precedence.

CSS palettes contain one `:root` block of the supported variables and optional
`color-scheme`. Comments are allowed. KNOT reads those values for both CSS and the
canvas graph; arbitrary selectors, imports and CSS expressions are not supported.
Use `create` to see all available variables, or inspect the complete
[Midnight palette](../src/knot/presentation/themes/midnight.css). Values omitted
from a custom file inherit Matrix defaults; copy a complete palette when changing
between light and dark backgrounds.

### JSON palettes

Existing JSON palettes remain supported in the same folder or by explicit path:

```json
{
  "schema_version": 1,
  "name": "Ocean",
  "colors": {
    "accent": "#60c7ff",
    "background": "#061520",
    "text": "#d8edfa",
    "entity": "#247a99",
    "accepted": "#60c7ff"
  },
  "fonts": {"ui": "system-ui, sans-serif", "graph": "sans-serif"}
}
```

For a complete light theme, copy
[Paper](../src/knot/presentation/themes/paper.json) and edit its values. The
[Matrix definition](../src/knot/presentation/themes/matrix.json) lists every supported
colour token and the `ui`, `body` and `graph` font roles. `color_scheme` accepts
`dark` or `light`. Colours use hexadecimal RGB/RGBA values; fonts name locally
available families. Unknown fields, invalid colours and unsupported versions fail
before an existing export is overwritten. CSS palettes use `--font-ui`, `--font-body`
and `--font-graph` for the three font roles. Invalid theme selections leave the
saved preference unchanged. A missing selected file produces an error; select
`matrix` again or use an explicit export override to recover.

Keep personal theme files outside the application checkout. They may live in the
data repository if you want to share them with that dataset. Export embeds the
resolved palette, so recipients need neither the theme file nor internet access.
Contributed bundled themes live under `src/knot/presentation/themes/`; adding a
valid CSS or JSON file with a lowercase slug filename makes it selectable by name.

Colours and fonts apply to both the page and the canvas. Shapes, claim status,
inference dashes, note links, evidence and filtering retain their meanings. Choose
readable contrast and distinct status colours; the loader validates syntax, not
accessibility. The default Matrix colours are described below.

## Existing full-network viewer

Use `--legacy` for the previous full-network viewer and its export-time filters:

```sh
knot view --legacy                         # Unified graph with overlapping theme hubs
knot view --legacy --focus "Example project"
just visualise-theme systems-and-flow
just visualise-frameworks          # Competencies, mastery criteria and requirements
just visualise-frameworks Mentoring
```

These commands open the default browser, including the Windows browser when running
in WSL. Outputs default to `views/graph.html` or `views/frameworks.html` under the
selected dataset. They open the legacy graph-only page; the **Live network** button
in the current interface is a different presentation of the shared Graph/Library data.
To export without opening a browser:

```sh
knot view --legacy --frameworks --output /tmp/frameworks.html --no-open
# Direct module invocation is also export-only by default:
PYTHONPATH=src .venv/bin/python -m knot.presentation.visualise
```

Legacy exports require at least one matching note or claim. `--frameworks` needs
imported framework claims; a note-only dataset has none. Topic examples also need
matching memberships. If filtering finds nothing, export stops with an explicit
error rather than generating an empty graph.

The controls and visual roles below apply to this legacy page. For the current
interface, use [Library reading](#read-in-library) and
[focused/live exploration](#focused-and-live-graph-exploration) above.

### Read and explore the graph

Notes and entities share the graph. Free writing without claim relationships
appears as blue boxes; notes used in claims appear as purple ovals. Blue **links to**
edges connect notes and retain your explanation;
blue **about** edges show saved note–entity associations. These connections do not
imply agreement, causation or claim acceptance. You do not need to create an entity
just to put a note on the graph. Regenerate the snapshot after saving links.

Use the sidebar to toggle individual notes, entities, node types and themes immediately.
Search narrows the checkbox list by title, preferred name, historical alias, type or ID.
All search words must occur, in any order (for example, `example project`
finds **Example project notes**). **Show matches** enables
those entities; **Hide non-matches** enables the matches and hides all other entities.
Other filters still apply, and visible claims require both endpoints. Clear the search
and click **Show matches** to restore all entities. Selecting an entity's name or graph
node opens its notes and visible connections; **Focus on this entity/note** shows
its immediate connections, including incoming links. **Entity details** exposes the stable identifier and
historical names. Names remain complete on the canvas and in the inspector.
While focused, **+1 hop** adds the next layer of relationships around every visible
note and entity. Repeat to keep exploring; the focus label shows the current depth.
**−1 hop** removes one outer layer, stopping at direct connections (one hop).
**Reset hops** returns straight to direct connections, and **Clear focus** restores the wider
view. Expansion respects active filters and hidden nodes, follows relationships in
both directions, and does not traverse theme hubs or literal attributes. The button
disables when there are no more matching connections in the exported snapshot.
Selections within a filter group match any selected value; different groups combine.
Theme filters match each claim's memberships, with **No assigned theme** available.

**Associated notes** appear above the connections, with the first note open for reading.
Expand other note titles to compare ideas, and **Sources & qualifications** to inspect
the original quotations, source locations and pinned revisions. Authorship identifies
who wrote the text. Only current notes explicitly associated with that
entity appear; selecting a note also displays its own body. Matching names do not establish an association. An entity without one
shows an empty message. Claim filters affect the connections, not these contextual
notes, and displaying a note does not accept any claim.

The Claims section filters review status and Explicit/Inferred origin for claims.
Knowledge kind and theme filters also apply to notes and their links. Purple ovals
represent notes that participate in claim relationships; blue boxes represent other
associated or standalone notes. These are visual roles, not new stored note types.
A note used in both roles appears once as a purple oval. **Associated notes** toggles
note navigation and standalone notes; claim endpoints remain visible according to
the claim filters. Green circles represent subjects or source documents. Evidence
stays in the inspector as exact quotations, with no evidence nodes on the graph.
Accepted-only views hide standalone notes and note navigation, which has no claim
review status. Click a blue link to read its explanation and move to either endpoint.
Literal values appear as **attributes** of their subject, with separate counts, rather
than independent nodes. Select an attribute to read its exact value, datatype, language
where recorded, original quotations and review details. The same claim filters apply
to attributes; a subject with only attributes remains visible when those values match.
Click a connection or graph edge to keep its exact quotations, source paths, rationale
and review details under **Evidence cited by this claim**. Bright green edges are accepted;
muted green edges are unreviewed; dashed edges are inferred. Use
`--accepted-only` with the Python command to show accepted assertions only.
Diamond nodes and faint dotted links show separately reviewed theme membership, excluded
from the claim count and hidden when only Accepted claims are selected. **Theme hubs**
toggles their display independently of the theme filters. `--no-themes` omits these
theme links from the export. `--theme <slug>` and `--kind <kind>` select narrower exports.
Filtered note exports retain immediate linked context, including incoming links.
`--frameworks` exports framework claims only.
At overview zoom, theme links become faint solid lines for smoother rendering; zooming
closer restores their dots. Inferred claim edges keep their dashes at every zoom level.
Framework definitions and other text values are inspectable attributes. Their RDF
values are displayed separately from exact source quotations, since a source-backed
definition can be an interpretation. The viewer omits literal paragraphs as nodes.

Drag nodes and scroll to zoom. Layout pauses after the initial arrangement; filters
preserve positions by default. **Spacing** adjusts separation from 1× to 4×, starting
at a roomier 1.5×. Changing it animates the visible layout without changing your zoom.
With Live layout off, **Rearrange** runs a short animation and pauses after settling
or four seconds.
Enable **Live layout** to keep the layout responsive to dragging, spacing and filters;
it can settle naturally but stays enabled. **Pause layout** freezes it and switches
Live layout off. **Fit view** frames the current graph. Resetting filters preserves
your spacing and live-layout preference. Edge labels can be hidden to reduce clutter. Counts show
visible versus exported entities/claims, and **Reset all filters** restores the exported
snapshot. It cannot restore claims excluded by command-line filters.

The views embed their assets and require no server or internet
connection. Filtering changes visibility only; the HTML still contains all exported
evidence. Regenerate it to see newly saved notes or review decisions. Generated HTML
is ignored by Git. [ADR 0026](../design_decisions/0026-live-offline-graph-filters.md) records
the filter and evidence semantics.

Use `just quality` to check citations and receive naming/granularity warnings after
authoring. [ADR 0028](../design_decisions/0028-meaningful-entity-names-and-value-presentation.md)
defines naming and value-presentation conventions.
