# Chapter 4 decision register

<!-- Generated from config/analysis/chapter4_decision_register_v2.json. Do not edit by hand; run python/scripts/chapter4_v2_analysis.py render-register. -->

Register version 2.11.0, for specification `chapter4_consolidated_analysis_spec` version 2.0.5 (sha256 `939b2ec30e5e5a7c1868fa499c076c999aba5e7b8b06aac22b8a2a2b72779b1f`).

Statuses: **confirmed** (adopted by the author for implementation; not supervisor approval), **proposed** (not adopted), **unresolved** (open; the affected module is disabled or shown as pending), **superseded** (historical, kept for provenance). No entry has been executed on real data under this specification.

source_document_date is the date of the document named in recorded_in, which records the decision; it is not an adoption date and no adoption date is recorded anywhere. Where that document itself states an earlier date for the decision, the date is kept separately in date_stated_by_source and labelled as stated, not verified. Historical files without a document date carry null.

## Summary

| ID | Title | Status | Implementation | Recorded in (document date) |
| --- | --- | --- | --- | --- |
| D-SCOPE-01 | Main comparison of implemented workflow packages | confirmed | not_applicable | SRC-CRITERIA (2026-10-25) |
| D-REG-01 | Registry of 31 primary procedures | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-REG-02 | Inputs that are not primary procedures | confirmed | implemented | SRC-BRIEF (2026-10-25) |
| D-REG-03 | Procedure ID strings and comparator naming on ties | proposed | implemented | SRC-IMPL-STEP1 (2026-10-26) |
| D-SAMP-01 | Samples B, I27, R, H1 supports and H2 I_m | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-AGG-01 | Primary VA aggregation: complete hierarchy | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-AGG-02 | G outside I27 | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-SCORE-01 | Zero-credit class scores and balanced score on B | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-SCORE-02 | Thresholds | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-CMP-01 | Three G margins and unfiltered comparator search | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-KAPPA-01 | Cohen's kappa as complementary measure | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-BOOT-01 | Framework bootstrap | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-BOOT-02 | Scope of the framework bootstrap | confirmed | implemented | SRC-BRIEF (2026-10-25) |
| D-ROB-01 | Six deterministic omissions for G | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-ROB-02 | Leave-one-campaign-out for a standalone leader | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-FW-01 | Non-correspondence, similarity and unresolved differences | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-FW-02 | Shared errors and directional corrections | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-FW-03 | Three-state conclusions | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-FIRTH-01 | Firth logistic regression on a fixed common sample | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-FIRTH-02 | Fit diagnostics, failures and proximity | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-H1-01 | H1 observed repeated-call variation | confirmed | implemented | SRC-MAP (2026-10-25) |
| D-H2-01 | H2 confirmed core | confirmed | implemented | SRC-H2 (2026-10-25) |
| D-H2-02 | H2 temporal sensitivity filter | unresolved | decision_pending | SRC-H2 (2026-10-25) |
| D-H2-03 | H2 ancillary procedures | unresolved | decision_pending | SRC-H2 (2026-10-25) |
| D-H2-04 | Policy for an incomplete H2 Holm family | unresolved | decision_pending | SRC-BRIEF (2026-10-25) |
| D-H2-05 | P-S ANOVA candidate | proposed | historical_retained | SRC-BRIEF (2026-10-25) |
| D-H3-01 | H3 point contrast on I27 | confirmed | implemented | SRC-MAP (2026-10-25) |
| D-H3-02 | H3 inference procedure | unresolved | decision_pending | SRC-BRIEF (2026-10-25) |
| D-H3-03 | H3 complementary comparison on available samples | proposed | decision_pending | SRC-BRIEF (2026-10-25) |
| D-H4-01 | H4 descriptive coefficient dispersion | confirmed | implemented | SRC-CRITERIA (2026-10-25) |
| D-E1-01 | E1 descriptive correspondence | confirmed | implemented | SRC-MAP (2026-10-25) |
| D-IO-01 | Analytical input from task-level records | confirmed | implemented | SRC-BRIEF (2026-10-25) |
| D-IO-02 | Binding of collections to the three design models | unresolved | decision_pending | SRC-IMPL-STEP1 (2026-10-26) |
| D-REP-01 | Reporting structure and provenance | confirmed | implemented | SRC-BRIEF (2026-10-25) |
| D-CHRON-01 | Chronology of data exposure | unresolved | not_applicable | SRC-BRIEF (2026-10-25) |
| D-SAMP-02 | Empirical B from the planned list, with a visible planned-versus-actual check | confirmed | implemented | SRC-AUTHOR-REVIEW-STEP2 (2026-10-26) |
| D-BOOT-03 | Bootstrap of the third G margin | confirmed | implemented | SRC-AUTHOR-REVIEW-STEP3 (2026-10-26) |
| D-ROB-03 | Identification of the standalone candidate | confirmed | implemented | SRC-AUTHOR-REVIEW-STEP3 (2026-10-26) |
| D-FW-04 | Composition of the evidence-to-framework rows | proposed | implemented | SRC-IMPL-STEP3 (2026-10-26) |
| D-SCORE-03 | Exact comparison of floating-point values | confirmed | implemented | SRC-AUTHOR-REVIEW-STEP3 (2026-10-26) |
| D-FIRTH-03 | Specified step-halving limit prevents certified convergence | unresolved | decision_pending | SRC-IMPL-STEP4 (2026-10-26) |
| D-FIRTH-04 | Separation diagnostic by linear programming | proposed | implemented | SRC-IMPL-STEP4 (2026-10-26) |
| D-FIRTH-05 | Operational usability rules for a Firth fit | proposed | implemented | SRC-IMPL-STEP4 (2026-10-26) |
| D-CH4-STRUCT | Proposed four-section structure of Chapter 4 | proposed | not_applicable | SRC-AUTHOR-MSG-CH4STRUCT (2026-10-26) |
| D-EXPORT-01 | Chapter 3 protocol files and data-free Chapter 3 tests in the review package | confirmed | implemented | SRC-AUTHOR-MSG-EXPORTFIX (2026-10-26) |
| D-EXPORT-02 | Observed fields removed from the Chapter 3 files; the cost estimator stays out | proposed | implemented | SRC-AUTHOR-MSG-EXPORTV3 (2026-10-26) |
| D-EXPORT-03 | The review package carries the plan, the launch code and the starting data, never evidence of a run | confirmed | implemented | SRC-AUTHOR-MSG-EXPORTV3 (2026-10-26) |

## Confirmed decisions

### D-SCOPE-01: Main comparison of implemented workflow packages

The main comparison concerns the two implemented packages, adapted configuration benchmarking (CB) and variance-aware annotation (VA). It does not identify the isolated causal effect of aggregation across arms.

- Sources: SRC-BRIEF §4; SRC-MAP Revision 2; SRC-CRITERIA Revision 2 'Che cosa non viene dimostrato'
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: design; procedures
- Implementation: not_applicable
- Empirical execution: not_executed

### D-REG-01: Registry of 31 primary procedures

21 CB procedures (seven strategies by three models, designated generation), nine VA procedures (three prompts by three models, after S=3 aggregation) and the final aggregate G (S->P->M), each with a fixed unique ID.

- Sources: SRC-BRIEF §4; SRC-CRITERIA Appendix 'Campioni e comparatori'
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: procedures
- Implementation: implemented
- Empirical execution: not_executed

### D-REG-02: Inputs that are not primary procedures

The 27 raw VA component vectors are H3 inputs; the three within-model S->P vectors are H4 inputs. Neither joins the primary comparator set. Coincident vectors keep separate identities and are never deduplicated.

- Sources: SRC-BRIEF §4
- Version: Revision 2
- Recorded in: SRC-BRIEF
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: procedures
- Implementation: implemented
- Empirical execution: not_executed

### D-SAMP-01: Samples B, I27, R, H1 supports and H2 I_m

B: fixed benchmark (planned 250; 32 HUMAN positives, 218 negatives). I27: all 27 planned VA calls valid. R: valid HUMAN, success, covariates and all 31 primary labels, fixed once before all fits. H1: complete triplets per model-prompt cell. H2 I_m: manifest-selected equal-order pair with six valid responses, never substituted by I27 or R. Membership and exclusion reasons are first-class outputs; no performance-based selection.

- Sources: SRC-BRIEF §4; SRC-CRITERIA Appendix; SRC-H2 §4
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: samples
- Implementation: implemented
- Empirical execution: not_executed
- Notes: Membership, exclusion reasons and class counts are implemented for B, I27, R, H1 supports and H2 I_m. H1 and H2 supports range over all benchmark items without using HUMAN.

### D-AGG-01: Primary VA aggregation: complete hierarchy

A VA configuration requires exactly the three planned valid S labels; G requires all 27 valid calls. Aggregation is hierarchical majority S->P->M, never pooled majority. Expected task identities are validated, not just counted. The historical two-valid-concordant rule is a separately named legacy rule and never a fallback.

- Sources: SRC-BRIEF §4; SRC-CRITERIA §5 and Appendix; SRC-MAP Revision 2 completeness note
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: H-AGG-01
- Specification: aggregation
- Implementation: implemented
- Empirical execution: not_executed
- Notes: The legacy rule is legacy_two_valid_concordant in aggregation.py, delegating to the unchanged historical module; the primary path never calls it.

### D-AGG-02: G outside I27

Outside I27, G is missing and receives zero correctness credit on B. Missing is never label 0.

- Sources: SRC-BRIEF §4; SRC-CRITERIA Appendix
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: aggregation.g_outside_i27
- Implementation: implemented
- Empirical execution: not_executed

### D-SCORE-01: Zero-credit class scores and balanced score on B

A_c(j) = valid correct labels in class c / all campaigns of B in class c; BA = mean of A_+ and A_-. Missing earns zero but stays missing; it is never a false positive or false negative. Valid correct, valid incorrect and missing counts and coverage are reported by class. The old identity accuracy + FP share + FN share = 1 is not reused on B without a missing share.

- Sources: SRC-BRIEF §5; SRC-CRITERIA §1; SRC-MAP scoring note
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: H-SCORE-01
- Specification: scores
- Implementation: implemented
- Empirical execution: not_executed
- Notes: Per-procedure missing counts by class and reason are a secondary output (missing_by_procedure), as the author asked in the Step 2 review.

### D-SCORE-02: Thresholds

A_+ >= 0.75 and A_- >= 0.925 (on B at least 24 correct positives and 202 correct negatives); BA margin >= 0.03; absolute Firth coefficient distance from HUMAN <= 0.41. Applied to unrounded values; inclusive boundaries.

- Sources: SRC-BRIEF §5; SRC-CRITERIA §§1-4
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: scores.thresholds
- Implementation: implemented
- Empirical execution: not_executed

### D-CMP-01: Three G margins and unfiltered comparator search

Report G minus best CB, G minus best post-S VA and G minus best of all 30 configurations (the minimum of the first two). The comparator search is not filtered to adequate configurations. A standalone configuration is compared with every other primary procedure, including G. Selection-conditional intervals are not independent validation.

- Sources: SRC-BRIEF §5; SRC-CRITERIA §2 and Appendix
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: H-CMP-01
- Specification: comparisons
- Implementation: implemented
- Empirical execution: not_executed

### D-KAPPA-01: Cohen's kappa as complementary measure

Kappa is complementary in RQ1 pairwise agreement and RQ2 agreement with HUMAN, on explicitly declared valid paired support. Undefined kappa is NA, never 1. No adoption threshold. Conventional valid-response metrics may remain secondary.

- Sources: SRC-BRIEF §5; SRC-CRITERIA Appendix 'Intervalli delle annotazioni'
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: kappa
- Implementation: implemented
- Empirical execution: not_executed
- Notes: Kappa against HUMAN: framework.kappa_exact(vector, None, ...) exactly (kappa_vs_human_B in the framework output) and FrameworkReplicates.kappa(vector) per replicate. Pairwise kappa: framework.kappa_exact(a, b, ...) in the 465-pair table. Undefined kappa is None/NaN, never 1.

### D-BOOT-01: Framework bootstrap

10,000 paired campaign resamples on B, stratified by HUMAN (planned 32 positives and 218 negatives per replication), NumPy Generator(PCG64(20261024)), lexicographically ordered campaign IDs, positives drawn before negatives in each replication; two-sided percentile 95% intervals with linear interpolation for A_+, A_-, BA, coverage and declared paired margins; original comparator fixed; decisions on point estimates; kappa interval only if all replicates are defined. Indices or weights saved with their hash, sample IDs, generator, seed and software versions.

- Sources: SRC-BRIEF §6; SRC-CRITERIA Appendix 'Intervalli delle annotazioni'
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: H-BOOT-01
- Specification: framework_bootstrap
- Implementation: implemented
- Empirical execution: not_executed
- Notes: Interval publication extends the brief's kappa-specific rule (SRC-BRIEF §6) to every statistic: an interval is published only when every replicate is defined; otherwise the defined share is reported and the interval is unavailable. Under the stratified design A+, A-, BA, coverage and margins are always defined, so in the current output only kappa can be suppressed. Recorded as an extension at the author's request (SRC-AUTHOR-REVIEW-STEP3).

### D-BOOT-02: Scope of the framework bootstrap

The framework bootstrap is not applied to H2 and is not used to settle the H3 inference conflict.

- Sources: SRC-BRIEF §6
- Version: Revision 2
- Recorded in: SRC-BRIEF
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: framework_bootstrap.not_applied_to
- Implementation: implemented
- Empirical execution: not_executed

### D-ROB-01: Six deterministic omissions for G

Omit each prompt globally and each model globally (18 calls per reduced panel), keeping B, original I27 and the original best-of-30 comparator fixed and recovering no campaign. Undetermined votes propagate as possibility sets; final ties earn 0.5 for this robustness score only, never in a regression. Margin >= 0.03 in all six; report the minimum.

- Sources: SRC-BRIEF §6; SRC-CRITERIA §3 and Appendix 'Sei omissioni per G'
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: robustness.g_omissions
- Implementation: implemented
- Empirical execution: not_executed

### D-ROB-02: Leave-one-campaign-out for a standalone leader

Fix the original candidate; omit each campaign of B in turn; recompute class denominators and the strongest of the other 30 procedures; require margin >= 0.03 in every omission and report the minimum. The two robustness checks are not ranked on a shared stability scale and are not repeated-call estimates for CB.

- Sources: SRC-BRIEF §6; SRC-CRITERIA §3 and Appendix
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: robustness.standalone_leave_one_out
- Implementation: implemented
- Empirical execution: not_executed

### D-FW-01: Non-correspondence, similarity and unresolved differences

Pairwise class-balanced non-correspondence counts two missing labels as non-correspondence and reports valid disagreement and missingness separately. Practical similarity uses the whole group meeting annotation adequacy and evaluable HUMAN proximity (at least two members; every pair < 0.03 and <= 0.41). Unresolved differences inspect the fixed 465 pairs; a failed fit is not a substantive difference.

- Sources: SRC-BRIEF §7; SRC-CRITERIA 'Similarità e casi irrisolti' and 'Tre stati'
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: framework
- Implementation: implemented
- Empirical execution: not_executed
- Notes: Implemented on B; conditions that need Firth evidence stay not_evaluable until Step 4 supplies it.

### D-FW-02: Shared errors and directional corrections

Fixed groups S_CB (21), S_VA (9) and S_ALL (30), G excluded. Per class: J, E, U, E/N_c, U/N_c, E/J when J > 0, U - E. E+ >= 9 or E- >= 17 (and the same for U, missingness included) is sufficient for group-wide annotation inadequacy; not a new adoption condition. Shared VA failures also prevent G from being correct; the CB-only implication is not extended to G. Directional corrections for the 36 VA pairs on the BA scale are descriptive.

- Sources: SRC-BRIEF §7; SRC-CRITERIA 'Errori condivisi e compensazioni osservate'
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: framework.shared_error_groups; framework.directional_corrections
- Implementation: implemented
- Empirical execution: not_executed

### D-FW-03: Three-state conclusions

Every framework conclusion returns value, rule, sample, comparator, status and reason, with status satisfied, not_satisfied or not_evaluable. A known failure establishes not_satisfied; adequate annotations with unavailable downstream evidence are not_evaluable; 'none adequate' only if all procedures are known failures.

- Sources: SRC-BRIEF §7; SRC-CRITERIA 'Tre stati senza confondere assenza e mancanza di evidenza'
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: framework.status_values; framework.overall_adequacy
- Implementation: implemented
- Empirical execution: not_executed
- Notes: Implemented on B; conditions that need Firth evidence stay not_evaluable until Step 4 supplies it.

### D-FIRTH-01: Firth logistic regression on a fixed common sample

success ~ LABEL + lgoal + C(subcategory) + C(year) with intercept on fixed R; supplied lgoal; R-observed levels sorted as strings with the first as reference; one control matrix for all fits; no silent row removal. 35 fits: 31 primary procedures, HUMAN re-estimated on R, and three within-model S->P labels for H4. Reference implementation R logistf 1.26.1 with the standard penalty, the specified controls and profile intervals; no FLIC, FLAC, tuning, alternative estimator or fallback.

- Sources: SRC-BRIEF §8; SRC-CRITERIA 'Specificazione statistica downstream'; SRC-MAP Revision 2 'Current scope'
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: H-FIRTH-01; H-MLE-01
- Specification: downstream
- Implementation: implemented
- Empirical execution: not_executed
- Notes: R logistf 1.26.1 installed on 2026-10-26 as a Windows binary from CRAN into the R 4.4 user library only. The binary was built under R 4.4.3 (Built: 'R 4.4.3; x86_64-w64-mingw32; 2026-04-22 05:00:52 UTC; windows') and runs under R 4.4.1 (2024-06-14 ucrt), x86_64-w64-mingw32, Windows 11 x64. Added to the user library: foreach 1.5.2, formula.tools 1.7.1, glmnet 4.1-10, iterators 1.0.14, jomo 2.7-6, mice 3.19.0, mitml 0.4-5, operator.tools 1.6.3.1, ordinal 2025.12-29, pan 1.9, shape 1.4.6.1, ucminf 1.2.3. Other dependencies were already installed (for example Matrix 1.7-0, mgcv 1.9-1, jsonlite 1.8.9). No Rtools, no compilation. Every adapter run records the full session (R version, build R version, all recursive dependency versions, loaded packages). R is located through CHAPTER4_V2_RSCRIPT, a local untracked local_paths.json, or PATH. See D-FIRTH-03 for the convergence blocker.

### D-FIRTH-02: Fit diagnostics, failures and proximity

Pre-fit checks (both success classes, LABEL variation, N > p, full rank with SVD tolerance max(N,p)*eps*s_max), linear-programming separation diagnostic (recorded, not a failure), certified convergence, finite estimates and positive LABEL variance, both profile endpoints converged and finite. HUMAN failure makes all distances unavailable; a procedure failure affects only its own. Proximity |beta_j - beta_HUMAN| <= 0.41 is an application tolerance, not an equivalence test; MLE and Firth are never mixed.

- Sources: SRC-BRIEF §8; SRC-CRITERIA 'Diagnostiche e regola dei fallimenti'
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: downstream.pre_fit_checks; downstream.failure_propagation
- Implementation: implemented
- Empirical execution: not_executed
- Notes: Operational details in D-FIRTH-04 (separation LP) and D-FIRTH-05 (usability).

### D-H1-01: H1 observed repeated-call variation

Per model-prompt combination, proportion of complete binary triplets that are not unanimous; mean pairwise disagreement equals two thirds of it on the same support and is not a separate finding. Incomplete support reported separately. No CB repeated-call comparator.

- Sources: SRC-BRIEF §9 H1; SRC-MAP Revision 2 'H1 equivalent scales'
- Version: Revision 2
- Recorded in: SRC-MAP
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: modules.h1
- Implementation: implemented
- Empirical execution: not_executed
- Notes: h1.py: complete binary triplets per cell; the 2/3 identity is checked on every call and reported as an identity; partial triplets reported by valid count; no CB comparator.

### D-H2-01: H2 confirmed core

Equal label_order pair chosen from the planned manifest alone; integrity issue if the two-plus-one pattern or within-repetition constancy fails; I_m requires six valid responses in the selected pair, third-prompt invalidity does not exclude; Q_i = (2 S_A - T)^2 / 6, exact conditional upper tail including equality, no mid-p or Monte Carlo; three model tests with Holm at familywise 0.05, raw and adjusted p-values; N = 0 not evaluable; no informative strata gives p = 1 with a flag; two descriptive rates on I_m without a between-minus-within contrast; HUMAN does not enter. Sufficient assumptions documented.

- Sources: SRC-BRIEF §9 H2; SRC-H2 §§3-7, §10, §14
- Version: H2 sheet version 2 (2026-10-18), consolidated 2026-10-25
- Recorded in: SRC-H2
- Source document date: 2026-10-25
- Date stated by the source (not verified): 2026-10-17
- Date note: Date of the source document that records the decision; it is not an adoption date. SRC-H2 §14 states that these points were explicitly agreed on 17 October 2026. Stated by the source; not independently verified.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: H-MAP-01
- Specification: modules.h2_core; samples.H2_I_m
- Implementation: implemented
- Empirical execution: not_executed
- Notes: h2.py: pair from the planned manifest (samples.h2_supports); exact conditional upper tail including equality in integers and fractions through 6Q = n15 + n3 + 4X + 8Z; Holm over the three planned tests with raw and adjusted p-values. When fewer than three tests are evaluable the family is reported as incomplete and no adjusted p-value is produced, pending D-H2-04. The tests derive the conditional law by enumerating the 20 allocations with itertools.

### D-H3-01: H3 point contrast on I27

Delta_BA = BA(G) - mean over the 27 component vectors of BA, on I27 with its actual class denominators; not evaluable if either class is absent; uniform mean, not the best component, the post-S means or a pooled majority; no 0.03 margin; sensitivity/specificity contributions and coverage reported.

- Sources: SRC-BRIEF §9 H3; SRC-H3 §§4-5; SRC-MAP Revision 2
- Version: Revision 2
- Recorded in: SRC-MAP
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date. SRC-H3 records the contrast as agreed without a date and states that its own date is a summary date; the date given is that of SRC-MAP Revision 2, which records the contrast.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: modules.h3_point_contrast
- Implementation: implemented
- Empirical execution: not_executed
- Notes: h3.py: G and the 27 component vectors on I27 with its class denominators; uniform mean; sensitivity and specificity contributions checked to add up to Delta_BA; coverage and exclusions reported; no 0.03 margin.

### D-H4-01: H4 descriptive coefficient dispersion

Nine post-S and three within-model post-S->P Firth coefficients on R; all 12 usable for the full contrast. SD with denominator 3 per prompt, D_pre their mean, D_post the SD of the three post-P coefficients, Delta_D = D_pre - D_post; percent only when D_pre > 0; ranges; three separate outcomes. No minimum reduction, bootstrap or p-value.

- Sources: SRC-BRIEF §9 H4; SRC-CRITERIA 'Dispersione downstream prima e dopo i prompt'; SRC-MAP Revision 2
- Version: Revision 2
- Recorded in: SRC-CRITERIA
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: modules.h4
- Implementation: implemented
- Empirical execution: not_executed

### D-E1-01: E1 descriptive correspondence

BA(R) against absolute Firth distance from HUMAN(R) for the 31 primary procedures; CB, post-S VA and G distinguished; overlapping identities kept; unavailable distances listed; BA(B) remains the decision score; no Spearman, p-value or regression.

- Sources: SRC-BRIEF §9 E1; SRC-MAP Revision 2 'E1 retained specification'
- Version: Revision 2
- Recorded in: SRC-MAP
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: modules.e1
- Implementation: implemented
- Empirical execution: not_executed

### D-IO-01: Analytical input from task-level records

The new analysis is built from validated task-level records and the planned design, never from old aggregate or report outputs. Slots distinguish planned-but-unobserved tasks, technical failures, terminal invalid responses and valid labels; duplicates and identity mismatches are integrity errors. Private paths enter only through an explicit data-root argument or a local binding outside version control. No loader suggests or launches new calls. Exercised with synthetic fixtures only in this phase.

- Sources: SRC-BRIEF §3, §11
- Version: 2026-10-25
- Recorded in: SRC-BRIEF
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: samples; aggregation.validate_expected_task_identities
- Implementation: implemented
- Empirical execution: not_executed

### D-REP-01: Reporting structure and provenance

Workflow comparison central; main report with coverage, performance profiles, three G margins, downstream coefficients and diagnostics, concise H1-H4/E1 and the evidence-to-framework table; details in appendices; pending modules visible; missing never shown as zero, failure or pass. Table 3.4B needs documentary evidence; missing cost is NA. Record model alias, returned identifier, route, settings sent versus omitted, parser version, UTC dates, spec version and code/dependency versions; historical collection settings are not retrospectively changed.

- Sources: SRC-BRIEF §10
- Version: 2026-10-25
- Recorded in: SRC-BRIEF
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: reporting
- Implementation: implemented
- Empirical execution: not_executed
- Notes: Implemented: the output catalogue keyed to analysis IDs with output tiers, the pending-status table, provenance headers and synthetic labelling (reporting.py, the synthetic example). Not implemented here: assembling the documentary evidence for Table 3.4B (B1-B4), which needs documents rather than code; those rows stay not_evaluable.

### D-SAMP-02: Empirical B from the planned list, with a visible planned-versus-actual check

For the real run B comes from the planned list of 250 campaigns and is not rebuilt from the data. A non-binary HUMAN label, a missing or extra campaign, or class sizes other than 250/32/218 appear as a visible planned-versus-actual check in the output, never as a silent exclusion or a hard-coded validity gate. Per-procedure missing counts are kept as a secondary output for coverage tables and appendices. A member of B without a binary HUMAN label appears as a visible integrity discrepancy; how it would be scored is not decided now.

- Sources: SRC-AUTHOR-REVIEW-STEP2; SRC-AUTHOR-REVIEW-STEP3
- Version: 2026-10-26
- Recorded in: SRC-AUTHOR-REVIEW-STEP2
- Source document date: 2026-10-26
- Date note: Date of the author's message in this coding chat that records the decision; the source is a chat message, not a document. It is not an adoption date. Reconfirmed in SRC-AUTHOR-REVIEW-STEP3.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: samples.B.empirical_membership; samples.B.planned_check
- Implementation: implemented
- Empirical execution: not_executed
- Notes: planned_benchmark_check (samples.py) lists such members under integrity_discrepancies and marks their scoring 'not decided (D-SAMP-02)'; missing_by_procedure (scores.py) gives the per-procedure missing counts.

### D-BOOT-03: Bootstrap of the third G margin

With the original comparators fixed, the third G margin (against the best of all 30 configurations) uses the fixed best-of-30 identity in every replicate. It equals the minimum of the other two margins at the point estimate, not necessarily in each replicate.

- Sources: SRC-AUTHOR-REVIEW-STEP2; SRC-AUTHOR-REVIEW-STEP3
- Version: 2026-10-26 (confirmed)
- Recorded in: SRC-AUTHOR-REVIEW-STEP3
- Source document date: 2026-10-26
- Date note: Date of the author's message in this coding chat that records the decision; the source is a chat message, not a document. It is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: framework_bootstrap.third_g_margin
- Implementation: implemented
- Empirical execution: not_executed
- Notes: Shown by test_framework_bootstrap.ReplicateTests.test_third_margin_is_the_minimum_only_at_the_point_estimate.
- Earlier status: proposed, recorded in SRC-AUTHOR-REVIEW-STEP2 (2026-10-26), proposal recorded at the author's request; awaiting confirmation

### D-ROB-03: Identification of the standalone candidate

The standalone candidate is the configuration with the highest BA on B among the 30 configurations, with ties named by the smallest procedure ID. Its leave-one-out check is computed even when its point margin fails, and the margin status is reported separately.

- Sources: SRC-AUTHOR-REVIEW-STEP3; SRC-IMPL-STEP3
- Version: 2026-10-26 (confirmed)
- Recorded in: SRC-AUTHOR-REVIEW-STEP3
- Source document date: 2026-10-26
- Date note: Date of the author's message in this coding chat that records the decision; the source is a chat message, not a document. It is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: robustness.standalone_leave_one_out.candidate_identification
- Implementation: implemented
- Empirical execution: not_executed
- Earlier status: proposed, recorded in SRC-IMPL-STEP3 (2026-10-26), implementation proposal

### D-SCORE-03: Exact comparison of floating-point values

Values that arrive as doubles, such as Firth coefficient distances, are compared with thresholds at the exact value of the double (Fraction(float)), never after rounding. The R adapter must therefore transmit coefficients at full double precision (Step 4).

- Sources: SRC-AUTHOR-REVIEW-STEP3; SRC-IMPL-STEP3
- Version: 2026-10-26 (confirmed)
- Recorded in: SRC-AUTHOR-REVIEW-STEP3
- Source document date: 2026-10-26
- Date note: Date of the author's message in this coding chat that records the decision; the source is a chat message, not a document. It is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: scores.thresholds.float_values
- Implementation: implemented
- Empirical execution: not_executed
- Earlier status: proposed, recorded in SRC-IMPL-STEP3 (2026-10-26), implementation proposal

### D-EXPORT-01: Chapter 3 protocol files and data-free Chapter 3 tests in the review package

This changes the earlier export rule (Step 6), which kept the whole historical suite python/tests/chapter3/ and the Chapter 3 configuration out of the review package. The package now also holds the Chapter 3 protocol files (rubric, label contract, Camuffo and Carlson prompt files), experiment definitions v1 and v3_hf_full, the DeepSeek Hugging Face route v1, manifest.py, runner_two_arm.py, chapter3_design.py and chapter3_execute.py, and the Chapter 3 tests that run without data/ and runs/: test_catalog, test_hierarchy, test_results, test_providers, test_manifest, test_runner_row_settings and their helper _fakes.py. Every other historical test stays private. test_catalog's check of all reference hashes is skipped where the third-party source paper is absent (it is not redistributed); a separate test checks the hashes of the four protocol files everywhere.

- Sources: SRC-AUTHOR-MSG-EXPORTFIX
- Version: 2026-10-26 (confirmed)
- Recorded in: SRC-AUTHOR-MSG-EXPORTFIX
- Source document date: 2026-10-26
- Date note: Date of the author's message in this coding chat that records the decision; the source is a chat message, not a document. It is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: none
- Implementation: implemented
- Empirical execution: not_executed
- Notes: Enforced by test_review_export.py (the selected modules are listed; no other module of python/tests/chapter3/ may be). The selected tests were scanned by file, line and category; they hold invented fixtures only (no observed values), so nothing was scrubbed. They read no file under data/ or runs/: the only call that would read the dataset (definitive manifest generation) is refused by its gates before any read in every test that makes it.

### D-EXPORT-03: The review package carries the plan, the launch code and the starting data, never evidence of a run

The review repository contains the plan and the code to launch the calls: experiment definitions (pilot and full, all three models), routes, rubric, prompts, labels, the two-arm execution script and the cost estimator. It contains no evidence that a run happened or how it went, and no outputs. Files that record observations enter as reviewer-facing derived copies: observed fields (outcomes of probes, smokes and pilots, token counts, real costs, real-run dates, corrections about earlier reports, paths to runs/) are removed, every settings field is unchanged, and a visible review_redaction field (JSON) or header comment (scripts) lists what was removed by path or line. Pilot and smoke item-id lists are plan when their selection is label-blind and deterministic, and stay. A file that cannot be redacted without changing its logic stays excluded. The starting data that no run generated (the benchmark dataset and the prompt source files the configurations refer to) are added under data/, each as an explicit allowlist entry; the Carlson paper and any third-party file not redistributed stay out. Provenance and redistribution licence of the starting data are to be confirmed by the author, and the repository stays private until then.

- Sources: SRC-AUTHOR-MSG-EXPORTV3
- Version: 2026-10-26 (confirmed)
- Recorded in: SRC-AUTHOR-MSG-EXPORTV3
- Source document date: 2026-10-26
- Date note: Date of the author's message in this coding chat that records the decision; the source is a chat message, not a document. It is not an adoption date.
- Decided by: author (researcher)
- Supervisor approval: not documented
- Supersedes: none
- Specification: none
- Implementation: implemented
- Empirical execution: not_executed
- Notes: Implemented by python/scripts/chapter4_v2_redact_for_review.py (paths and line numbers only; originals pinned by SHA-256 and left untouched) and by the export builder, whose blanket refusal of data/ became an exception limited to three named files pinned by SHA-256. test_review_export.py and test_hygiene.py enforce both. No test opens a file under data/.

## Proposals (not adopted)

### D-REG-03: Procedure ID strings and comparator naming on ties

Procedure IDs are built from planned design identifiers: cb::{model_key}::{template_id}, va_s::{model_key}::{template_id}, va_g::s_p_m, va_c::{model_key}::{template_id}::s{k}, va_sp::{model_key}. Among comparators with equal BA, the smallest ID in ascending lexicographic order is reported. Because 'cb::' sorts before 'va_s::', a cross-arm tie in the best-of-30 search is named after the CB procedure; the margin is unaffected.

- Sources: SRC-BRIEF §5 (lexicographic fixed IDs); SRC-CRITERIA Appendix (identifiers fixed in the manifest)
- Version: implementation proposal 2026-10-26
- Recorded in: SRC-IMPL-STEP1
- Source document date: 2026-10-26
- Date note: Date of the source document that records the decision; it is not an adoption date. Recorded by the Step 1 implementation report as a proposal.
- Decided by: implementation proposal
- Supervisor approval: not documented
- Supersedes: none
- Specification: procedures.id_scheme; procedures.comparator_tie_identity
- Implementation: implemented
- Empirical execution: not_executed
- Notes: Implemented as proposed (python/src/chapter3/chapter4_v2/procedures.py); the author keeps it as a proposal.

### D-H2-05: P-S ANOVA candidate

The existing P-S sum-of-squares decomposition remains outside the primary plan. It is not activated; no power simulation or new variance estimator is added.

- Sources: SRC-BRIEF §9 H2; SRC-H2 §2
- Version: candidate_analysis, proposed_not_approved
- Recorded in: SRC-BRIEF
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: not adopted
- Supervisor approval: not documented
- Supersedes: none
- Specification: modules.h2_ps_anova
- Implementation: historical_retained
- Empirical execution: not_executed
- Notes: Entry h2.h2_ps_anova exists and refuses to run; the historical candidate script is kept unchanged and is not used.

### D-H3-03: H3 complementary comparison on available samples

Has no adopted activation threshold and stays outside the primary implementation. Optional error/gain and stage decompositions are documented as identities, not required outputs.

- Sources: SRC-BRIEF §9 H3; SRC-H3 §§9-10
- Version: open
- Recorded in: SRC-BRIEF
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: not adopted
- Supervisor approval: not documented
- Supersedes: none
- Specification: modules.h3_complementary_available_samples
- Implementation: decision_pending
- Empirical execution: not_executed

### D-FW-04: Composition of the evidence-to-framework rows

A1, A2 and A4 combine the criteria of SRC-CRITERIA with the three-valued rule. A3 is satisfied when at least one directional correction is observed, with reciprocity and the >= 0.03 level reported as descriptive levels. A5 is derived from A1, A4 and the differences over the 465 pairs (not_evaluable when a preference is not evaluable, or when no annotation difference is observed and downstream distances are unavailable). A6 is satisfied when a group has shared failures sufficient for group-wide inadequacy or no procedure is adequate; otherwise it is not_evaluable while overall adequacy is unresolved and not_satisfied when an adequate procedure exists. B1-B4 are not_evaluable until the documentary evidence is assembled. A3 is descriptive and never enters per-procedure overall adequacy, which combines annotation adequacy and HUMAN proximity only. 'None adequate' in A6 requires every procedure to be a known failure; if any is merely not evaluable, overall adequacy stays unresolved.

- Sources: SRC-IMPL-STEP3
- Version: 2026-10-26
- Recorded in: SRC-IMPL-STEP3
- Source document date: 2026-10-26
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: implementation proposal
- Supervisor approval: not documented
- Supersedes: none
- Specification: framework.evidence_table_composition
- Implementation: implemented
- Empirical execution: not_executed
- Row sources:
  - A1_adequate_stable_leader: SRC-CRITERIA 'Esiti delle tabelle', row A1; §§1-4 (adequacy, advantage, stability, proximity)
  - A2_adequate_similar_procedures: SRC-CRITERIA 'Esiti delle tabelle', row A2; 'Practical similarity and error complementarity'; Appendix 'Similarità e casi irrisolti'
  - A3_compensating_errors: SRC-CRITERIA 'Esiti delle tabelle', row A3; 'Correzione reciproca'
  - A4_adequate_advantageous_aggregate: SRC-CRITERIA 'Esiti delle tabelle', row A4; §§1-5; Appendix 'Sei omissioni per G'
  - A5_unresolved_differences: SRC-CRITERIA 'Esiti delle tabelle', row A5; 'Tre stati senza confondere assenza e mancanza di evidenza' (465 pairs)
  - A6_shared_errors_or_none_adequate: SRC-CRITERIA 'Esiti delle tabelle', row A6; 'Soglia derivata dall adeguatezza'; 'Tre stati' (none adequate)
  - B1_human_validation: SRC-CRITERIA 'Esiti delle tabelle', row B1; 'Condizioni contestuali', row 'Validazione umana'; SRC-BRIEF §10
  - B2_downstream_sensitivity: SRC-CRITERIA 'Esiti delle tabelle', row B2; 'Condizioni contestuali', row 'Sensibilità inferenziale'
  - B3_resources: SRC-CRITERIA 'Esiti delle tabelle', row B3; 'Condizioni contestuali', row 'Risorse'; SRC-BRIEF §10
  - B4_inferential_stakes: SRC-CRITERIA 'Esiti delle tabelle', row B4; 'Condizioni contestuali', row 'Posta inferenziale'

### D-FIRTH-04: Separation diagnostic by linear programming

Z = diag(2y - 1) X with every coefficient boxed in [-1, 1], solved with HiGHS (scipy). Separation exists if max sum(Z b) subject to Z b >= 0 exceeds 1e-7; it is complete if max t subject to Z b >= t exceeds 1e-7; coefficient j would diverge without penalisation if b_j can be non-zero (beyond 1e-7) inside that cone. Recorded, never a Firth failure.

- Sources: SRC-IMPL-STEP4; SRC-CRITERIA 'Diagnostiche e regola dei fallimenti'
- Version: 2026-10-26
- Recorded in: SRC-IMPL-STEP4
- Source document date: 2026-10-26
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: implementation proposal
- Supervisor approval: not documented
- Supersedes: none
- Specification: downstream.separation_lp
- Implementation: implemented
- Empirical execution: not_executed
- Notes: No supplied document fixes bounds, solver or tolerance: SRC-BRIEF §8 line 149 refers to 'the specified linear-programming diagnostic'; SRC-CRITERIA line 88 requires an LP diagnostic and cites only the detectseparation documentation as reference [2] (line 215). These choices therefore have nothing in the documents to be compared against.

### D-FIRTH-05: Operational usability rules for a Firth fit

Point usable: |log-likelihood change| <= lconv, max |score| <= gconv and max |beta change| <= xconv, as reported by logistf (conv), inclusive; finite coefficients and covariance; LABEL variance > 0; firth TRUE and flic FALSE. Interval usable: for both LABEL profile limits, |log-likelihood deviation| <= profile lconv, |last beta change| <= profile xconv, fewer than profile maxit iterations, finite limit, and logistf reports the LABEL interval as profile likelihood. The null-model iterations logistf runs for p-values are not part of usability. A HUMAN fit that is not fully usable (point and interval) counts as a HUMAN failure. A point-only fit is descriptive and cannot pass downstream adequacy. The working rule (HUMAN without a usable interval counts as a HUMAN failure) is stricter than the brief's wording; both readings and their consequences are recorded under 'readings'. Marked for the author's decision.

- Sources: SRC-IMPL-STEP4; SRC-CRITERIA 'Diagnostiche e regola dei fallimenti'
- Version: 2026-10-26
- Recorded in: SRC-IMPL-STEP4
- Source document date: 2026-10-26
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: implementation proposal
- Supervisor approval: not documented
- Supersedes: none
- Specification: downstream.usability_details; downstream.usable_fit; downstream.usable_interval
- Implementation: implemented
- Empirical execution: not_executed
- Readings:
  - working_rule_strict: A HUMAN fit without a usable profile interval counts as a HUMAN failure: every distance is unavailable. Consequence: Every HUMAN-proximity condition is not_evaluable. A4 (and A1) become not_evaluable unless another condition is a known failure; A2 is not_evaluable when two or more procedures are annotation-adequate; A5 is not_evaluable when a preference is not evaluable.
  - brief_literal: SRC-BRIEF §8: 'A usable point estimate without a usable interval may be shown descriptively, but cannot pass downstream adequacy. HUMAN failure makes all distances unavailable.' Read literally, a HUMAN point estimate that is usable without its interval is not a HUMAN failure, so distances remain computable from it; each procedure still needs its own usable interval to pass. Consequence: A4 can be satisfied if G's own fit is usable and |beta_G - beta_HUMAN| <= 0.41, even when HUMAN's interval failed; A5 can then be not_satisfied because a preference is established.
- Author decision needed: yes

### D-CH4-STRUCT: Proposed four-section structure of Chapter 4

Chapter 4 reduced to four sections: 4.1 design and execution; 4.2 analytical approach; 4.3 results, with 4.3.1 annotation results and workflow comparison and 4.3.2 downstream results; 4.4 framework application and discussion. H1-H4 and E1 stay as analysis identifiers inside those sections. Full prompts, algorithm details, extended matrices and exhaustive tables go to appendices. The Chapter 4 analysis map Revision 2 is kept unedited as history. No analytical module changes, and output labels stay keyed to analysis IDs, never to section numbers.

- Sources: SRC-AUTHOR-MSG-CH4STRUCT; SRC-BRIEF §10; SRC-MAP Revision 2
- Version: 2026-10-26
- Recorded in: SRC-AUTHOR-MSG-CH4STRUCT
- Source document date: 2026-10-26
- Date note: Date of the author's message in this coding chat that records the proposal; the source is a chat message, not a document. It is not an adoption date.
- Decided by: author's tentative proposal (not adopted)
- Supervisor approval: not documented
- Supersedes: none
- Specification: reporting.chapter_structure; reporting.labels
- Implementation: not_applicable
- Empirical execution: not_executed
- Notes: A writing structure, not code. The code keeps labels on analysis IDs and adds output tiers (reporting.py), which hold under any chapter structure.

### D-EXPORT-02: Observed fields removed from the Chapter 3 files; the cost estimator stays out

Applying D-EXPORT-03, the twenty-one Chapter 3 files that record observations (config/chapter3_experiment.json, experiment definitions v2-v9, all eleven route records and python/scripts/chapter3_execute_two_arm.py; experiment v3_hf_full and the DeepSeek Hugging Face route v1 were added after a re-scan of the rebuilt export found further observed fields in them) enter the package as derived copies written by chapter4_v2_redact_for_review.py; each lists its removals. In the script only comments, the docstring and string constants change (lines 12, 106-118 and 669-673 of the original). python/scripts/chapter3_estimate_cost.py stays out: its two calibration constants are observed values and are the defaults of --chars-per-token and --output-tokens, so removing them would change what the estimator computes.

- Sources: SRC-AUTHOR-MSG-EXPORTFIX
- Version: 2026-10-26 (revised)
- Recorded in: SRC-AUTHOR-MSG-EXPORTV3
- Source document date: 2026-10-26
- Date note: Date of the author's message in this coding chat that set the redaction rule; which fields count as observed is the classification proposed in this implementation, awaiting the author's review. It is not an adoption date.
- Decided by: remediation proposed in this implementation; awaiting the author's review
- Supervisor approval: not documented
- Supersedes: none
- Specification: none
- Implementation: implemented
- Empirical execution: not_executed
- Notes: Checks: every original matches its pinned SHA-256; JSON copies parse; for each experiment copy the prompt catalogue and the fixture manifests of every scope equal those of the original except the config_sha256 of the experiment itself; validate_config accepts both versions of chapter3_experiment.json; the script's syntax tree, with string constants masked, equals the original's. Hashes recorded inside the copies refer to the originals. No execution contract is included; a contract binds the exact files it authorises by SHA-256.
- Earlier status: proposed, recorded in SRC-AUTHOR-MSG-EXPORTFIX (2026-10-26), remediation proposed in this implementation; earlier version: the twenty files were excluded from the package

## Unresolved decisions

### D-H2-02: H2 temporal sensitivity filter

Provisional W <= 300 seconds, W = last completion minus first start over the six selected calls. Needs metadata-only confirmation before any sensitivity result. Not enabled in the primary pipeline; real logs are not inspected now.

- Sources: SRC-BRIEF §9 H2 extensions; SRC-H2 §9a
- Version: provisional since 2026-10-17
- Recorded in: SRC-H2
- Source document date: 2026-10-25
- Date stated by the source (not verified): 2026-10-17
- Date note: Date of the source document that records the decision; it is not an adoption date. SRC-H2 §9a states that the provisional threshold was accepted on 17 October 2026 as explicitly provisional. Stated by the source; not verified.
- Decided by: pending
- Supervisor approval: not documented
- Supersedes: none
- Specification: modules.h2_temporal_sensitivity
- Implementation: decision_pending
- Empirical execution: not_executed
- Notes: Entry h2.h2_temporal_sensitivity exists and refuses to run (DecisionPending).

### D-H2-03: H2 ancillary procedures

Holm over a separate temporal family and a paired campaign bootstrap appendix for the two rates (10,000 resamples, percentile 95%) are proposals awaiting final ratification. HUMAN stratification is not imported from the framework.

- Sources: SRC-BRIEF §9 H2 extensions; SRC-H2 §9e, §10, §13
- Version: proposals of 2026-10-18
- Recorded in: SRC-H2
- Source document date: 2026-10-25
- Date stated by the source (not verified): 2026-10-18
- Date note: Date of the source document that records the decision; it is not an adoption date. SRC-H2 §14 states that the central review proposed these on 18 October 2026. Stated by the source; not verified.
- Decided by: pending
- Supervisor approval: not documented
- Supersedes: none
- Specification: modules.h2_ancillary_bootstrap_and_temporal_holm
- Implementation: decision_pending
- Empirical execution: not_executed
- Notes: Entry h2.h2_ancillary_bootstrap exists and refuses to run (DecisionPending).

### D-H2-04: Policy for an incomplete H2 Holm family

The planned three-test family is not shrunk if a model is unavailable or not evaluable. Until a policy is recorded, such a family is reported as incomplete rather than as a two-test adjusted result.

- Sources: SRC-BRIEF §9 H2; SRC-H2 §7
- Version: open
- Recorded in: SRC-BRIEF
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: pending
- Supervisor approval: not documented
- Supersedes: none
- Specification: modules.h2_incomplete_family_policy
- Implementation: decision_pending
- Empirical execution: not_executed

### D-H3-02: H3 inference procedure

Documentary conflict. Historical H3 sheet: ordinary paired campaign bootstrap, 10,000 replications, two-sided 95% percentile interval plus a one-sided test of Delta > 0, with p-value inversion conventions, zero ties and any +1 adjustment not fixed. Newer central map: paired HUMAN-stratified bootstrap, 10,000 replications, PCG64 seed 20261024, two-sided percentile interval, reconciliation with the directional test pending. The H3 inference entry stays disabled with decision_pending until one procedure is recorded; neither is computed.

- Sources: SRC-BRIEF §9 H3; SRC-H3 §§7-8; SRC-MAP Revision 2 'H3 estimation and test'
- Version: open
- Recorded in: SRC-BRIEF
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: pending
- Supervisor approval: not documented
- Supersedes: none
- Specification: modules.h3_inference
- Implementation: decision_pending
- Empirical execution: not_executed
- Recommendation: Retain the newer stratified estimation plan without an additional p-value (SRC-BRIEF §9). A recommendation, not a ratified change. If the historical directional test is retained, its numerical conventions must be fixed first.
- Notes: Entry h3.h3_inference exists, refuses to run (DecisionPending) and cannot be enabled by the specification while D-H3-02 is open. The framework bootstrap is not connected to H2 or H3.

### D-IO-02: Binding of collections to the three design models

The design's model keys (terra_5_6, sonnet_5, deepseek_v4_pro) must be bound to specific collection logs and manifests. The repository holds more than one DeepSeek collection (Hugging Face router and OpenRouter routes), and historical instructions forbid pooling the routes or treating either as the reference. Which collection supplies the DeepSeek slot must be confirmed by the author before any empirical run.

- Sources: SRC-BRIEF §3 (planned design); historical CLAUDE.md 'Do not pool the OpenRouter and Hugging Face routes'
- Version: open
- Recorded in: SRC-IMPL-STEP1
- Source document date: 2026-10-26
- Date note: Date of the source document that records the decision; it is not an adoption date. Raised by the Step 1 implementation report; not settled by the brief.
- Decided by: pending
- Supervisor approval: not documented
- Supersedes: none
- Specification: design.collection_binding
- Implementation: decision_pending
- Empirical execution: not_executed

### D-CHRON-01: Chronology of data exposure

The author currently states that nobody has viewed these data. Earlier sheets record audits and exposure (SRC-H2 §8 and §13; SRC-H3 'Trasparenza temporale'), and SRC-CRITERIA records a previously observed DeepSeek coefficient. To be reconciled by the author's factual clarification, distinguishing generation, automatic computation, AI/tool access, human inspection of annotations and human reading of inferential results. Annotation generation predates the 25 October revision regardless; it is not a pre-generation registration.

- Sources: SRC-BRIEF §10; SRC-CRITERIA 'Version and timing'; SRC-H2 §13; SRC-H3 §15
- Version: open
- Recorded in: SRC-BRIEF
- Source document date: 2026-10-25
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: pending
- Supervisor approval: not documented
- Supersedes: none
- Specification: status_note
- Implementation: not_applicable
- Empirical execution: not_executed

### D-FIRTH-03: Specified step-halving limit prevents certified convergence

The specified fit control (maxit 1000, maxhs 25, maxstep 5, lconv = gconv = xconv = 1e-6, collapse FALSE, Newton-Raphson, zero start) does not let logistf 1.26.1 certify convergence on the invented designs tried. Facts (invented data only): (1) the installed package's formal defaults are maxhs 0 and maxit 25 for logistf.control, maxhs 0 and maxit 100 for logistpl.control; its help defines maxhs as the maximum number of step-halvings in one iteration. (2) Plain logistf calls reproduce the non-certification, and on six designs the adapter's coefficients, convergence values and iterations are bit-identical to plain logistf: the adapter is not the cause. (3) Varying the fit-control maxhs: 0 certifies in 4-13 iterations; 1 diverges (coefficients off by 1.6-4.4, penalised log-likelihood far lower); 5 and 25 stall at maxit with max |score| about 2e-2 to 1.3e-1 and coefficients 2.5e-4 to 5e-4 from the maxhs-0 fit, at a penalised log-likelihood about 1e-6 lower. Varying the profile-control maxhs (0, 1, 5, 25) leaves the LABEL limits unchanged to about 6e-14. (4) The earlier statement 'same estimate to about 1e-9' held only between fit maxhs 0 and logistf's own defaults, not against the specified fit. (5) On 40 invented designs closer to the real analysis (N 250, success about 30%, LABEL about 13% and associated with success, 15 subcategories with tiny levels, 6 years) the specified controls certified 0/40 and fit maxhs 0 certified 40/40. With weaker association the maxhs-0 fit had the higher penalised log-likelihood every time (LABEL gap at most 3.3e-4). With strong association (P(success | LABEL = 1) = 0.95) two designs had the non-certified specified fit 0.033 and 0.057 higher, and restarting maxhs 0 from that point certified there in one iteration: at least two certified stationary points exist, LABEL differing by 0.07-0.15 and tiny-level coefficients by about 1.1-1.3. (6) No supplied document states the origin of maxhs 25; SRC-CRITERIA says only that the tolerances and iteration limits are specific to that proposal.

- Sources: SRC-BRIEF §8 lines 151-153; SRC-CRITERIA 'Diagnostiche e regola dei fallimenti'; SRC-CRITERIA 'Diagnostiche e regola dei fallimenti' (line 90) and line 217; SRC-IMPL-STEP4; SRC-IMPL-STEP4-ADDENDUM; SRC-IMPL-STEP5-ADDENDUM
- Version: 2026-10-26
- Recorded in: SRC-IMPL-STEP4
- Source document date: 2026-10-26
- Date note: Date of the source document that records the decision; it is not an adoption date.
- Decided by: pending
- Supervisor approval: not documented
- Supersedes: none
- Specification: downstream.known_blocker; downstream.estimator.control
- Implementation: decision_pending
- Empirical execution: not_executed
- Notes: The choice must be fixed, and recorded as the author's decision, before any real-data run. No value is recommended here. The adapter test test_specified_controls_do_not_certify_convergence_here records the behaviour under the specified controls.
- Evidence note: Invented (synthetic) data only. The two designs in items 3-5 are deliberately extreme: tiny subcategories (one or two campaigns) and a LABEL that nearly or completely separates success. Whether the real design contains such cells is unknown; the real data were not inspected.
  - 1. Installed logistf 1.26.1 defaults: logistf.control maxit 25, maxhs 0, maxstep 5, lconv = gconv = xconv = 1e-5, collapse TRUE, fit NR; logistpl.control maxit 100, maxhs 0, maxstep 5, lconv = xconv = 1e-5. The help defines maxhs as the maximum number of step-halvings in one iteration.
  - 2. With the specified fit control (maxhs 25) the fit stalls at maxit without meeting gconv and xconv on every invented design tried; with fit-control maxhs 0 and nothing else changed it certifies. Only the fit control matters: varying the profile-control maxhs (0, 1, 5, 25) leaves the LABEL limits unchanged to about 6e-14. Plain logistf and the adapter give bit-identical fits.
  - 3. In two extreme designs the certified maxhs-0 point is a saddle, not a maximum: its score is about 2e-7 and 6e-7, but the Hessian of the penalised log-likelihood has one positive eigenvalue (about 0.11 and 0.15), and the penalised log-likelihood, evaluated from its definition, increases in both directions along that eigenvector (by the amount the eigenvalue predicts). The direction is almost entirely the coefficient of a two-campaign subcategory.
  - 4. In the same designs the genuine local maximum (all Hessian eigenvalues negative; penalised log-likelihood higher by 0.033 and 0.057) lies within about 3e-4 to 6e-4 of where the specified fit stopped, but the specified fit did not certify it. Restarting maxhs 0 from that point certified it in one iteration.
  - 5. The certification criteria (log-likelihood change, score and beta change within tolerance) cannot distinguish a saddle from a maximum.
  - 6. Between the saddle and the maximum, the LABEL coefficient differs by about 0.15 and 0.07 in the two designs; the coefficient of the tiny subcategory differs by about 1.1 and 1.3.
  - 7. The penalised log-likelihood computed from its definition matches the value logistf reports to about 1e-14 at every point examined; X'WX has a condition number of about 2e4.
  - Diagnostic scripts (dfirth03_diagnostics.R, dfirth03_realistic_detail.R, dfirth03_outlier.R, dfirth03_restart.R, dfirth03_verify.R, dfirth03_saddle.R, dfirth03_adapter_vs_plain.py) are kept outside the repository.
  - No uniqueness or non-uniqueness of the Firth estimate is inferred from theory, and no Hessian check or other rule is added to the pipeline.
- Options for the author:
  1. (a) Keep the specification as written: every fit fails certification and every downstream comparison is not evaluable.
  2. (b) Amend maxhs only, with a single predeclared value fixed in a new specification version; never a try-until-it-certifies loop. Certification would remain first-order: it cannot tell a saddle from a maximum.
  3. (c) Add a second-order check as an explicit, predeclared rule.
  4. (d) Other, as the author specifies.

## Sources

| ID | Title | Date | Kind |
| --- | --- | --- | --- |
| SRC-BRIEF | Implementation handoff for Claude Code and the coding chat | 2026-10-25 | document |
| SRC-CRITERIA | Criteri_consolidati_e_specifica_statistica_2026-10-25 | 2026-10-25 | document |
| SRC-MAP | Chapter4_analysis_map_2026-10-25 | 2026-10-25 | document |
| SRC-H2 | H2_analisi_decisioni_e_conclusioni_2026-10-25 | 2026-10-25 | document |
| SRC-H3 | H3_analisi_conclusioni_2026-10-25 | 2026-10-25 | document |
| SRC-IMPL-STEP1 | Step 1 implementation report (Chapter 4 v2) | 2026-10-26 | implementation report in this coding chat |
| SRC-IMPL-STEP2 | Step 2 implementation report (Chapter 4 v2) | 2026-10-26 | implementation report in this coding chat |
| SRC-AUTHOR-REVIEW-STEP2 | Author's message in this coding chat: review of Step 2 | 2026-10-26 | author message in this coding chat (not a document) |
| SRC-IMPL-STEP3 | Step 3 implementation report (Chapter 4 v2) | 2026-10-26 | implementation report in this coding chat |
| SRC-AUTHOR-REVIEW-STEP3 | Author's message in this coding chat: review of Step 3 | 2026-10-26 | author message in this coding chat (not a document) |
| SRC-IMPL-STEP4 | Step 4 implementation report (Chapter 4 v2) | 2026-10-26 | implementation report in this coding chat |
| SRC-IMPL-STEP4-ADDENDUM | Step 4 diagnostic addendum report (Chapter 4 v2) | 2026-10-26 | implementation report in this coding chat |
| SRC-IMPL-STEP5 | Step 5 implementation report (Chapter 4 v2) | 2026-10-26 | implementation report in this coding chat |
| SRC-IMPL-STEP5-ADDENDUM | Step 5 addendum report: D-FIRTH-03 verification (Chapter 4 v2) | 2026-10-26 | implementation report in this coding chat |
| SRC-AUTHOR-MSG-CH4STRUCT | Author's message in this coding chat: proposed Chapter 4 structure | 2026-10-26 | author message in this coding chat (not a document) |
| SRC-IMPL-STEP6 | Step 6 implementation report (Chapter 4 v2) | 2026-10-26 | implementation report in this coding chat |
| SRC-AUTHOR-MSG-EXPORTFIX | Author's message in this coding chat: fix of the review export | 2026-10-26 | author message in this coding chat (not a document) |
| SRC-AUTHOR-MSG-EXPORTV3 | Author's message in this coding chat: review package v3 (plan and launch code, starting data) | 2026-10-26 | author message in this coding chat (not a document) |

## Superseded historical rules and statements

| ID | Title | Superseded by | Retained as |
| --- | --- | --- | --- |
| H-AGG-01 | Two-valid-concordant hierarchy as the primary rule | D-AGG-01 | Named legacy rule legacy_two_valid_concordant_v1 for provenance; never a fallback. The historical module and its constant are not edited. |
| H-SCORE-01 | Valid-support accuracy and error shares as primary scores | D-SCORE-01 | Secondary conventional metrics on declared valid support. |
| H-CMP-01 | Carlson comparator as an open decision | D-CMP-01 | Historical documents are kept unedited. |
| H-FIRTH-01 | Firth recorded as not approved and absent | D-FIRTH-01 | Historical files unedited. The legacy assertions still describe the historical v1 map and module correctly; they are relabelled as historical with a link to D-FIRTH-01 when the Firth module lands (Step 4). |
| H-MLE-01 | MLE logit as the downstream estimator | D-FIRTH-01 | Historical replication of the Carlson-Burbano specification, documented as prior work; no new MLE run; never mixed with Firth. |
| H-BOOT-01 | Item-cluster bootstrap v1 for annotation intervals | D-BOOT-01 | Historical configuration and outputs unedited; not reused for the framework bootstrap. |
| H-MAP-01 | Analysis map Revision 2: H2 sheet not available | D-H2-01 | The H2 sheet was recovered (SRC-H2); the H3 conflict remains open under D-H3-02. |
