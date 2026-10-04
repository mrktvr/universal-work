# Documents and data procedure

## Route and inspect

1. Use the installed document, spreadsheet, presentation, PDF, or connected-file skill for the actual format and operation.
2. Inspect the source artifact before choosing an edit or conversion method.
3. Preserve requested structure, formulas, semantic roles, formatting, and relationships.
4. Establish the deliverable, audience, editing scope, and required storage destination.
5. Record source file identifiers, versions, sheet or tab names, and relevant ranges.
6. Keep the original available when a transformation could remove information.

## Define the data contract

- Identify column meanings, data types, keys, row grain, units, currencies, locale, and timezone.
- Distinguish transaction time, reporting period, and extraction time.
- Define filters, exclusions, joins, denominator choices, and treatment of missing values.
- Inspect duplicates, malformed values, hidden rows, active filters, and merged or multirow headers.
- Distinguish blank, zero, unavailable, and not applicable values; do not silently substitute one for another.
- Confirm whether displayed values, stored values, or formulas are the required source of truth.
- Resolve ambiguities that change calculations before reporting precise results.

## Transform with provenance

1. Work from a known source version or consistent snapshot.
2. Keep source cells, ranges, pages, or records traceable to each material output claim.
3. Use explicit formulas or reproducible transformations for derived quantities.
4. Preserve sufficient precision internally; apply rounding only at the appropriate presentation boundary.
5. Make assumptions and manual overrides visible near the affected output.
6. Avoid copying stale calculated values when recalculation is required.
7. Recheck the source version before applying edits to a live shared artifact.

## Verify meaning and calculations

- Recompute consequential totals independently from the underlying inputs where feasible.
- Reconcile subtotals, balances, percentages, and grouped results against the same included population.
- Test representative and boundary records through the actual transformation.
- Check joins for dropped records, duplicate expansion, and unintended many-to-many matches.
- Verify formulas reference the intended ranges and behave correctly for blanks and edge values.
- Inspect important claims against their source cells or passages, including qualifiers and units.
- Treat row counts, keyword presence, file existence, and successful export as structural checks only.
- Do not use structural checks alone to claim that calculations, interpretation, or content are correct.

## Render and inspect

1. Follow the format skill's required rendering and verification workflow.
2. Review the produced artifact, not only the source markup or object model.
3. Inspect pagination, clipping, overlaps, font substitution, hierarchy, and readable chart labels.
4. Verify tables and charts preserve units, scales, legends, ordering, and meaningful comparisons.
5. Check links, cross-references, page or slide order, and required editable elements.
6. Repair visible defects and rerender the affected output before delivery.
7. State a material rendering limitation if the required inspection cannot be completed.

## Deliver a usable artifact

- Save through the required durable destination and verify the saved file or native artifact is accessible.
- Provide the requested file format and a direct artifact link using the environment's conventions.
- Summarize the result and any material data or compatibility limitations.
- Do not claim live data, complete coverage, or preserved editability without checking it.
- Before handoff or compaction, record source versions, transformation rules, output location, verification evidence, and remaining completion criteria.
