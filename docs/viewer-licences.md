# Embedded viewer software notices

Audited on 2026-11-09. This records the software embedded by KNOT's current
Graph/Library exporter and supported legacy exporter. It does not grant rights to
knowledge content, certify dependency security, or cover redistribution of a whole
Python environment or Pandoc binary.

Both exports carry KNOT's MIT licence, vis-network's MIT option and complete texts
for the bundled components below. Legacy exports also carry PyVis's BSD-3-Clause
notice. The texts live in [presentation assets](../src/knot/presentation/), under
`*-license.txt`, and are included by the existing package-data rule. Required public
third-party names and emails in these notices are attribution, not dataset content.

## Evidence and exact scope

The installed PyVis assets and BSD notice were byte-compared with the published
[PyVis 0.3.2 wheel](https://pypi.org/project/pyvis/0.3.2/#files). Its SHA-256 is
`5720c4ca8161dc5d9ab352015723abb7a8bb8fb443edeb07f7a322db34a97555`.
No package was installed and no upstream executable or build script was run.

The upstream [vis-network 9.1.2 release archive](https://registry.npmjs.org/vis-network/-/vis-network-9.1.2.tgz)
contains the JS, CSS and source map used for comparison:

- PyVis's JavaScript matches `dist/vis-network.min.js` after newline normalisation,
  replacing upstream nonbreaking spaces with ordinary spaces and removing the final
  newline. These are the complete observed differences; KNOT does not change the JS.
- PyVis's CSS is exactly `styles/vis-network.min.css` with the final source-map
  comment removed. Its data-URI images are part of this upstream asset.
- The source map identifies 422 dependency source entries from the 11 packages
  below. Every entry was matched against its corresponding release file, allowing
  newline normalisation. Exact versions came from the tagged
  [release lockfile](https://github.com/visjs/vis-network/blob/v9.1.2/package-lock.json).
  This checks the code actually bundled, rather than copying the full development
  dependency list into the notices.
- Source comments were inspected for additional attribution. The vis-util bundle
  contains the complete Andrei Mackenzie Levenshtein MIT notice and credits the
  adapted Johannes Baagøe Alea algorithm. Both are retained, including the original
  Alea MIT text preserved by its
  [source mirror](https://github.com/nquinlan/better-random-numbers-for-javascript-mirror/blob/7a1bb58541cde248faaa1453a0f8691cc15ef79a/LICENSE.md).
  The mirror distinguishes code licensing from its wiki's content licence; no wiki
  article is bundled.

The compared upstream JS SHA-256 is
`6e30a2350474cdf92a0932c6d55b8adcb91929066817ed3eec7b87907a4612f3`;
its source map SHA-256 is
`20359c0b06bae162aaf84c6381b6084759644b87131aafde9f04fbae2e4b0c88`.
The vis-network licence is taken from its release `LICENSE-MIT`, also available at
the [tagged upstream source](https://github.com/visjs/vis-network/blob/v9.1.2/LICENSE-MIT).

## Known advisory applicability

An OSV package-version check on 2026-11-09 identified the following matches.
The affected implementations were checked against the exact JavaScript fingerprint
and corresponding release source map recorded above:

| Advisory and matched package | Affected implementation | Evidence in this bundle |
| --- | --- | --- |
| [GHSA-968p-4wvh-cqc8](https://github.com/advisories/GHSA-968p-4wvh-cqc8), @babel/runtime-corejs3 7.17.8 | `wrapRegExp` named-group replacement helper | No `wrapRegExp` source entry or occurrence in the source-map bodies. |
| [GHSA-w5hq-g745-h8pq](https://github.com/advisories/GHSA-w5hq-g745-h8pq), uuid 8.3.2 | Buffer writes in `v3`, `v5` and `v6` | The source map includes only `rng`, `regex`, `validate`, `stringify` and `v4`; the affected implementations are absent. |

These package-version matches therefore do not identify affected code in this
fingerprinted viewer bundle. The conclusion applies only to these two advisories
and the recorded asset bytes; it is not general security clearance for the packages,
KNOT or future exports. Repeat the applicability check when assets change.

## Bundled components

Links in the last column identify immutable-version release archives containing
the named licence files. Full texts, including each copyright statement, are in
[the dependency notice bundle](../src/knot/presentation/vis-network-dependencies-license.txt).
Where a project offers MIT or Apache-2.0, this export uses its MIT option.

| Bundled package | Licence used | Release licence file |
| --- | --- | --- |
| @babel/runtime-corejs3 7.17.8 | MIT | [LICENSE](https://registry.npmjs.org/@babel/runtime-corejs3/-/runtime-corejs3-7.17.8.tgz) |
| core-js-pure 3.21.1 | MIT | [LICENSE](https://registry.npmjs.org/core-js-pure/-/core-js-pure-3.21.1.tgz) |
| regenerator-runtime 0.13.9 | MIT | [LICENSE](https://registry.npmjs.org/regenerator-runtime/-/regenerator-runtime-0.13.9.tgz) |
| tslib 2.3.1 | 0BSD | [LICENSE.txt and CopyrightNotice.txt](https://registry.npmjs.org/tslib/-/tslib-2.3.1.tgz) |
| keycharm 0.4.0 | MIT option | [LICENSE-MIT](https://registry.npmjs.org/keycharm/-/keycharm-0.4.0.tgz) |
| component-emitter 1.3.0 | MIT | [LICENSE](https://registry.npmjs.org/component-emitter/-/component-emitter-1.3.0.tgz) |
| @egjs/hammerjs 2.0.17 | MIT | [LICENSE.md](https://registry.npmjs.org/@egjs/hammerjs/-/hammerjs-2.0.17.tgz) |
| uuid 8.3.2 | MIT | [LICENSE.md](https://registry.npmjs.org/uuid/-/uuid-8.3.2.tgz) |
| timsort 0.3.0 | MIT | [LICENSE.md](https://registry.npmjs.org/timsort/-/timsort-0.3.0.tgz) |
| vis-util 5.0.3 | MIT option | [LICENSE-MIT](https://registry.npmjs.org/vis-util/-/vis-util-5.0.3.tgz) |
| vis-data 7.1.4 | MIT option | [LICENSE-MIT](https://registry.npmjs.org/vis-data/-/vis-data-7.1.4.tgz) |

The additional [PyVis notice](../src/knot/presentation/pyvis-license.txt) applies to
legacy template/binding code. Jinja2 and Python render the template locally; their
implementations are not copied into the HTML. The Graph/Library page uses KNOT's
own shell and reads only the audited vis-network JS/CSS from PyVis.

Neither exporter embeds Tom Select, Bootstrap or Pandoc implementation code.
KNOT disables PyVis's select/filter menus, strips the legacy template's Bootstrap
remote imports and uses separately installed Pandoc only as a converter. A future
menu, template, converter or asset change requires a fresh inventory.

## Export guards and maintenance

[The shared asset loader](../src/knot/presentation/viewer_assets.py) requires PyVis
0.3.2 and checks the following SHA-256 values over UTF-8 text after newline
normalisation. Legacy rendering uses the verified template/includes in memory;
caller-supplied PyVis templates and stock menus cannot silently widen the bundle.

| PyVis template-relative file | SHA-256 |
| --- | --- |
| `lib/vis-9.1.2/vis-network.min.js` | `f3c1229464749a6f5a80c80867189edfdc0198be0d015c3d770aff196cb6c0a1` |
| `lib/vis-9.1.2/vis-network.css` | `2e82d445ad5878ea881652470ce632601f8f55f1b99e6ebecdff8614600e6d0e` |
| `template.html` (legacy) | `cc42e96b51f546f0057f680b1ddc77a0d09ee33a89144b188c16af5bb16bc348` |
| `lib/bindings/utils.js` (legacy) | `3113c73317c30c99eaafbc782916160ce7d23183a148615da0496643e9560cb0` |

Changed versions or bytes stop export before replacing an existing file. Do not
merely refresh these hashes to silence an error: compare the new release and source
map, review its complete notices, update the licence files and this inventory,
then verify both generated HTML files and installed-package resources.

[Regression tests](../tests/test_viewer_licences.py) check complete bundled notices,
legacy PyVis attribution, exclusion of unused menu assets, changed-asset/version
rejection and preservation of an earlier export on failure. Existing viewer tests
also check offline resources and literal evidence handling. A test cannot establish
ownership or legal clearance; this audit records the supplied licences and the
exact software to which the notice bundle applies.
