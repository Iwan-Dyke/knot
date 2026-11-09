# ADR 0034: Commit and push knowledge through the local CLI

- Status: Accepted
- Date: 2026-11-07
- Implementation: Implemented
- Documentation reviewed: 2026-11-07

The mixed-repository layout below was subsequently extended by
[ADR 0043](0043-local-datasets-and-optional-git.md). Current `knot push` and
`knot refresh` use the selected dataset's repository, with legacy `<git-root>/data`
support retained. See the [dataset guide](../docs/datasets.md#git-refresh-and-push).

## Context

The owner captures notes from arbitrary terminal directories using the installed
launcher and wants to commit and push without navigating to the checkout.
Application development and knowledge edits can coexist in the same working tree.

## Decision

Add `knot push` using Git subprocess arguments, the existing launcher and configured
branch upstream. Show knowledge changes and pending commits, then use a nonempty
commit-message prompt as the instruction to commit and push. Stage `data/` together
so registry entries, manifests, snapshots and curation remain in one commit. Exclude
drafts, views and locks explicitly, in addition to respecting Git ignore rules.
Reject unrelated staged files rather than changing the owner's index selections.

Use normal Git commits and non-forced pushes. Failed pushes retain local commits;
retrying with no new data pushes existing commits without making another commit.
Use a separate `knot refresh` command for an explicit fast-forward-only pull before
capture. Require a clean tracked and untracked working tree, respecting ignore
rules. Explicitly disable rebase and autostash regardless of user Git defaults.
Do not automate conflict resolution, upstream selection or credential configuration.

## Consequences

This small wrapper uses existing Git history and authentication without another
synchronisation system. Application edits need a separate development commit.
Push operates on branch history, so previously committed application changes are
also pushed; display pending commits and document this distinction. Concurrent
edits during the interactive operation follow normal Git working-tree semantics;
finish note capture before running the command. A commit failure can leave data
staged for inspection and retry. Tests use disposable local bare remotes.

Refresh updates the entire checkout, so application code can change alongside
knowledge. It does not install dependencies. A divergent branch requires owner
resolution in Git; silently merging note registries could break knowledge history.

The installed capture-to-push test exposed Git rejecting ignored draft and lock
paths when passed as add exclusions. Enumerate changed, nonignored knowledge files
first, then stage their exact literal paths using a NUL-delimited stream. This also
handles spaces, newlines and deletions without shell interpolation.
