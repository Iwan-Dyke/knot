# ADR 0017: Review theme membership independently of claims

- Status: Accepted
- Date: 2026-11-03
- Implementation: Implemented
- Documentation reviewed: 2026-11-07
- Extends: ADR 0016 (theme review was previously deferred)

## Context

The user has asked the assistant to review theme assignments, accept straightforward
matches and leave uncertain cases for later discussion. Keyword matching produces
false positives from document titles, incidental vocabulary and ambiguous words.
Changing a rule alone would not preserve an explicit acceptance or rejection.

## Decision

Keep a version-controlled theme review register in `data/organisation/theme-reviews.json`.
Record a decision and rationale for each reviewed assertion/theme pair, attributed
to the actual reviewer. Assistant review is labelled as such; it is not human
certification. Accepting topic relevance changes neither assertion review status,
knowledge kind, entity identity nor the origin of the theme inference.

Pin each record's review to its projected content fingerprint and each theme's
identifier, label and scope description. Rebuilds retain matching decisions. Changed
record content, identity projection or theme meaning makes the old decision stale;
it cannot silently remain accepted. Changing keyword suggestions alone cannot
override a current explicit acceptance or rejection.

Emit reviewable ThemeMembership resources in the organisation graph with target
assertion, theme, effective status, rationale and reviewer. Keep rejected assignments
inspectable but exclude them from active theme links. Unreviewed assignments remain
clearly marked. Entity/theme links are navigation derived from incident assertions;
an accepted supporting membership does not certify all claims about that entity.

Use the existing file-first rebuild command. Catalogue edits and review-register
changes retain history through version control; a dedicated editing UI or general
append-only event protocol for theme reviews is outside this increment. Assertion
review events remain immutable under ADR 0010.

## Review scope

Judge the subject matter of the record, not every word in its quotation. In
particular, a framework's title or PDF footer cannot make every competency about
data engineering. Software release promotion is distinct from career progression;
technical constraints alone do not establish a systems-thinking connection.
Prefer a few relevant themes and preserve genuinely uncertain assignments for
discussion. A framework requirement is about a competency, not evidence of personal
achievement or independent corroboration.

## Consequences and checks

Explicit reviews require more metadata than keyword tags, but make corrections
durable and explainable without changing source assertions. Synthetic tests must
cover acceptance, rejection, undecided membership, changed inputs/definitions,
idempotent rebuilds and independence from assertion review. Existing assertion
fingerprints and source files must remain unchanged.
