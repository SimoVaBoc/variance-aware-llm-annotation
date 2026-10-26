# Reviewer guide

This guide maps each confirmed requirement of the Chapter 4 plan to the module that
implements it and the tests that check it, and lists every item that is still open or
only proposed. Decision IDs refer to the decision register
(`docs/chapter4_v2/decision_register.md`). All tests use invented data.

Run the suite with
`python -B -m unittest discover -s python/tests/chapter4_v2 -v`
(test files are in `python/tests/chapter4_v2/`). Tests in `test_firth_r.py` need R with
logistf 1.26.1 and are reported as skipped otherwise.

## Confirmed requirements

| Requirement | Decision | Module | Tests |
| --- | --- | --- | --- |
| Versioned specification, exact thresholds, spec identity on outputs | D-SCORE-02 | `spec.py`, `provenance.py` | `test_spec`, `test_provenance` |
| Decision register: statuses, document dates (never adoption dates), no supervisor-approval claims | — | `decisions.py` | `test_decision_register` |
| Task-level input; four slot states; duplicates and mismatches are integrity errors | D-IO-01 | `inputs.py`, `io_boundary.py` | `test_inputs`, `test_io_boundary` |
| No access to private data or network in tests; imports start nothing | D-IO-01 | `_guard.py` | `test_guard`, `test_imports`, `test_hygiene` |
| Registry of 31 primary procedures; 27 H3 components and 3 H4 vectors kept apart; no deduplication | D-REG-01, D-REG-02 | `procedures.py` | `test_procedures_aggregation` |
| Primary aggregation 3/3 and 27/27, hierarchical S -> P -> M, named legacy rule never a fallback | D-AGG-01, D-AGG-02 | `aggregation.py` | `test_procedures_aggregation` |
| Samples B, I27, R, H1 and H2 supports with reasons and class counts; no performance-based selection; planned-versus-actual check | D-SAMP-01, D-SAMP-02 | `samples.py` | `test_samples_scores`, `test_framework_quantities` |
| Zero-credit class scores, balanced score, coverage; missing never a false positive or negative | D-SCORE-01 | `scores.py` | `test_samples_scores` |
| Thresholds inclusive and exact; floats compared at the exact double | D-SCORE-02, D-SCORE-03 | `thresholds.py` | `test_thresholds_comparisons` |
| Three G margins, unfiltered comparator search, lexicographic tie naming | D-CMP-01 | `comparisons.py` | `test_thresholds_comparisons` |
| Kappa complementary, NA never 1 | D-KAPPA-01 | `framework.py`, `framework_bootstrap.py` | `test_kappa` |
| Framework bootstrap: PCG64(20261024), lexicographic IDs, positives then negatives, 10,000 replicates, saved indices, linear percentiles, fixed comparators, interval only if every replicate is defined | D-BOOT-01, D-BOOT-02, D-BOOT-03 | `framework_bootstrap.py` | `test_framework_bootstrap` |
| Six G omissions with possibility sets; 1/2 only as a robustness score; original I27 fixed | D-ROB-01 | `robustness.py` | `test_robustness` |
| Leave-one-campaign-out for a fixed standalone leader | D-ROB-02, D-ROB-03 | `robustness.py` | `test_robustness` |
| Non-correspondence (both missing counts), similarity over the whole group, 465 pairs | D-FW-01 | `framework.py` | `test_framework_quantities` |
| Shared errors J/E/U, 9/17 sufficiency, directional corrections | D-FW-02 | `framework.py` | `test_framework_quantities` |
| Three-state conclusions; known failure versus not evaluable | D-FW-03 | `thresholds.py`, `framework.py` | `test_thresholds_comparisons`, `test_framework_quantities` |
| Firth through R logistf 1.26.1, common design on R, pre-fit checks, SVD rank, separation LP, usability rules, HUMAN failure propagation | D-FIRTH-01, D-FIRTH-02 | `downstream.py`, `firth.py`, `r/firth_adapter.R` | `test_downstream`, `test_firth_assessment`, `test_firth_r` |
| H1: complete triplets, 2/3 identity, partial support apart | D-H1-01 | `h1.py` | `test_h1` |
| H2 core: planned pair, exact conditional law (derived by enumeration in the tests), Holm over three tests | D-H2-01 | `h2.py` | `test_h2` |
| H3 point contrast on I27; inference disabled | D-H3-01 | `h3.py` | `test_h3` |
| H4 dispersion, E1 correspondence | D-H4-01, D-E1-01 | `h4_e1.py` | `test_firth_assessment` |
| Report: labels on analysis IDs, output tiers, pending table, synthetic labelling | D-REP-01 | `reporting.py`, `synthetic.py` | `test_reporting`, `test_analysis_status` |

## Open decisions (nothing here is resolved in code)

| Item | Decision | What the code does meanwhile |
| --- | --- | --- |
| H3 inference procedure (ordinary versus HUMAN-stratified bootstrap; directional test) | D-H3-02 | `h3.h3_inference` refuses to run; the specification cannot enable it |
| H2 temporal sensitivity (provisional W <= 300 s) | D-H2-02 | `h2.h2_temporal_sensitivity` refuses to run |
| H2 appendix bootstrap and separate temporal Holm family | D-H2-03 | `h2.h2_ancillary_bootstrap` refuses to run |
| Policy for an incomplete H2 Holm family | D-H2-04 | The family is reported incomplete; no adjusted p-values; never shrunk |
| Firth convergence under the specified controls (maxhs) | D-FIRTH-03 | Fits are judged by the specified rules; the evidence note records the synthetic diagnostics |
| Binding of collections to the three design models | D-IO-02 | No empirical binding exists; empirical inputs are refused |
| Chronology of data exposure | D-CHRON-01 | Documentation only |

## Proposed working rules (in use, not adopted)

| Item | Decision |
| --- | --- |
| Procedure ID strings and tie naming | D-REG-03 |
| HUMAN without a usable profile interval counts as a HUMAN failure (stricter than the brief's wording; both readings recorded) | D-FIRTH-05 |
| Separation LP: bounds, solver, tolerance (no document fixes them) | D-FIRTH-04 |
| Composition of the Table 3.4A/B rows | D-FW-04 |
| P-S ANOVA candidate (outside the primary plan) | D-H2-05 |
| H3 complementary comparison on available samples | D-H3-03 |
| Four-section structure of Chapter 4 | D-CH4-STRUCT |
| Which fields of the Chapter 3 files count as observed and are removed from the derived copies; the cost estimator stays out | D-EXPORT-02 |

## Points worth checking

- `test_h2.LawTests` derives the conditional law of Q by enumerating the 20 allocations
  of six responses and compares it with both the module and the table in the
  specification.
- `test_framework_bootstrap` checks the random stream against a reference loop written
  from the specification and shows that a vectorised draw order changes the index hash;
  no test pins a value of the stream.
- `test_firth_r.test_specified_controls_do_not_certify_convergence_here` records the
  behaviour under the specified controls; the D-FIRTH-03 evidence note in the register
  explains it (synthetic, deliberately extreme designs).
- The thresholds are decimal strings compared as exact fractions; a double coefficient is
  compared at its exact value, so boundary cases cannot flip through rounding.

## Limits of this package

- No outputs and no empirical results. The starting data (benchmark dataset and prompt
  source files) are included under `data/` (D-EXPORT-03); their provenance and
  redistribution licence are to be confirmed by the author, so the repository stays
  private. No test opens them.
- Of the historical test suite only the six Chapter 3 modules that run without data are
  included (D-EXPORT-01); one of their tests is skipped because the third-party source
  paper is not redistributed.
- Twenty-one Chapter 3 files are reviewer-facing derived copies with their observed fields
  removed; each says what was removed (`review_redaction` field or header comment).
  Hashes recorded inside them refer to the originals. The cost estimator is not included
  (D-EXPORT-02). No execution contract is included, so no live run can be launched from
  the package.
- The R-dependent tests need a local R with logistf 1.26.1; otherwise they are skipped.
- Network access is blocked inside the test process; child processes started by the
  tests (the import probe, R) are not network-sandboxed, and neither needs the network.
