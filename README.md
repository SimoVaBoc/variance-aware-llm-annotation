# Chapter 4 consolidated analysis (v2): review package

This package contains the source code, specification and synthetic test suite of the
Chapter 4 analysis of a master's thesis on LLM-generated annotations as a measurement
instrument, together with the Chapter 3 annotation plan, the code that launches the
calls, and the starting data. It is meant for a methodological and code review.

**Keep this repository private.** It includes the starting data (the benchmark dataset
and the prompt source files, see "Starting data" below). Their provenance and
redistribution licence are still to be confirmed by the author; until then the
repository must not be made public or shared beyond the reviewers.

**It contains no outputs and no results.** No model responses, manifests, logs, probe,
smoke or pilot outcomes, costs or empirical outputs are included, and no empirical
result has been produced under this specification. Every number the Chapter 4 code
produces from this package comes from invented data and is labelled `synthetic`; no
test reads the starting data.

The analysis plan is recorded in `config/analysis/chapter4_analysis_spec_v2.json`
(machine-readable) and in the decision register
(`config/analysis/chapter4_decision_register_v2.json`, rendered as
`docs/chapter4_v2/decision_register.md`). Every output records the specification ID,
version and SHA-256, the code commit and whether the working tree was modified.

Start with `docs/chapter4_v2/reviewer_guide.md`, which maps each requirement to the
module and the tests that implement it and lists every open decision.

## Installation

Python 3.13 (the code was developed and tested with 3.13.0 on Windows).

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-review.txt
```

`requirements-review.txt` pins numpy and scipy (needed) and matplotlib (only for the
optional E1 plot).

### Optional: R and logistf for the Firth fits

The downstream regressions use R `logistf` 1.26.1 through a thin adapter. Python never
estimates a regression. Without R, the R-dependent tests are reported as **skipped** and
the synthetic example marks the downstream outputs `not_run`.

1. Install R 4.4 and `logistf` 1.26.1 (on Windows a CRAN binary into the R user library
   is enough; no compilation is needed).
2. Tell the code where `Rscript` is, in this order of precedence:
   - the environment variable `CHAPTER4_V2_RSCRIPT`;
   - a local, untracked `local_paths.json` at the repository root:
     `{"rscript": "<path to Rscript>"}` (listed in `.gitignore`; never commit it);
   - `Rscript` on `PATH`.

## Running the tests

From the repository root:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s python/tests/chapter4_v2 -v
```

`-B` stops Python from writing bytecode caches into the tree. The suite uses invented
fixtures only. A guard installed by `python/tests/chapter4_v2/_guard.py` refuses to open
or list anything under `data/`, `runs/` or a folder named `Codice_tesi_private`, before
the operating system is asked for the file, and every test blocks the socket calls that
open a network connection.

### Why the import test allows one standard-library call

`test_imports.py` imports every module in a fresh interpreter and fails if an import
opens a non-source file outside the Python installation, starts a process or opens a
connection. There is exactly one exception. On Windows, importing scipy loads
`numpy.testing`, which calls `platform.machine()`; when Python's WMI query fails (for
example on a machine with little free memory), the standard library's `platform` module
falls back to running `ver` through the shell. The test therefore allows exactly the
command line `<COMSPEC> /c "ver"` and the single path `nul` (its stdin), and nothing
else; a second test shows that any other process or file opened at import is still
caught.

## Synthetic worked example

```powershell
.\.venv\Scripts\python.exe -B python/scripts/chapter4_v2_synthetic_example.py --out <new folder>
.\.venv\Scripts\python.exe -B python/scripts/chapter4_v2_synthetic_example.py --out <new folder> --no-r
```

It builds an invented input (`chapter4_v2/synthetic.py`), runs the annotation framework
with the framework bootstrap, H1, the H2 core and the H3 point contrast, and, when R is
available, the Firth fits, H4 and E1. It writes a JSON report and a short Markdown
summary. Each output is keyed to analysis IDs (A1-A6, B1-B4, H1-H4, E1) and carries an
`output_tier` (`main` or `appendix`); the report always includes the table of pending
modules. With the specified Firth controls the fits do not certify convergence (open
decision D-FIRTH-03), and the report shows that instead of hiding it.

Other commands:

```powershell
.\.venv\Scripts\python.exe -B python/scripts/chapter4_v2_analysis.py status
.\.venv\Scripts\python.exe -B python/scripts/chapter4_v2_analysis.py validate
.\.venv\Scripts\python.exe -B python/scripts/chapter4_v2_analysis.py render-register --check
```

## Source map

All new code lives in `python/src/chapter3/chapter4_v2/`. The `chapter3` package name
is historical and kept because earlier frozen files depend on the paths.

| Module | Role |
| --- | --- |
| `spec.py` | Loads and validates the specification; exact thresholds; spec identity |
| `decisions.py` | Validates and renders the decision register |
| `provenance.py` | Output header: spec, commit, modified tree, software, data kind |
| `inputs.py` | Task-level input: four slot states, integrity errors |
| `io_boundary.py` | The only place files are read: explicit data root and input binding |
| `procedures.py` | Registry: 31 primary procedures, 27 H3 components, 3 H4 vectors |
| `aggregation.py` | Strict primary aggregation (3/3, 27/27, S -> P -> M); named legacy rule |
| `samples.py` | B, I27, R, H1 supports, H2 I_m; exclusion reasons; planned-versus-actual check |
| `scores.py` | Class-specific correctness with zero credit for missing; balanced score |
| `thresholds.py` | Criteria statuses (satisfied / not_satisfied / not_evaluable); exact comparisons |
| `analysis_status.py` | Descriptive statuses (computed / not_computable) |
| `comparisons.py` | Observed best comparators; three G margins; standalone margin |
| `framework_bootstrap.py` | HUMAN-stratified paired campaign bootstrap (PCG64, seed 20261024) |
| `robustness.py` | Six G omissions with possibility sets; leave-one-campaign-out |
| `framework.py` | Non-correspondence, kappa, shared errors, corrections, similarity, Tables 3.4A/B |
| `annotation_framework.py` | Runs the annotation-level framework in order |
| `downstream.py` | Common design on R, pre-fit checks, SVD rank, separation LP |
| `firth.py`, `r/firth_adapter.R` | R logistf adapter and the rules that judge each fit |
| `h1.py`, `h2.py`, `h3.py`, `h4_e1.py` | Focused analyses |
| `pending.py` | Entry points that refuse to run while their decision is open |
| `reporting.py` | Output catalogue (analysis IDs, tiers), pending table, report assembly |
| `synthetic.py` | Invented input for the worked example |

A small number of earlier modules of the same package (`analysis`, `bootstrap`,
`catalog`, `design`, `execution`, `hierarchy`, `results` and the modules they import)
are included because the new code reuses their parser, status constants, identifier
checks and the historical aggregation rule, which is kept only as a named legacy rule.
The Chapter 3 protocol files and execution code are described in the last section.

## Input schema (for the later empirical run)

The analysis reads task-level records, never earlier aggregate reports. Private files
enter only through an explicit data root and a local **input binding** (JSON, kept
outside version control) whose paths are relative to that root:

```json
{
  "binding_version": 1,
  "data_kind": "empirical",
  "dataset": {"path": "...", "encoding": "...", "item_id_prefix": "...", "expected_rows": 250},
  "collections": [
    {"model_key": "<design model key>", "collection_model_id": "<model_id in the logs>",
     "manifest": "...", "raw_logs": ["..."]}
  ]
}
```

- Dataset columns: `text` (read only to derive identifiers, never carried), `HUMAN`,
  `success`, `lgoal`, `subcategory`, `year`; item IDs follow the project convention.
- Manifest rows (one per planned call): `task_id`, `item_id`, `model_id`, `arm`,
  `template_id`, `sample_index`, `label_order`, `is_remediation` and the content hashes
  `text_sha256`, `prompt_sha256`, `system_prompt_sha256`, `payload_sha256`,
  `config_sha256`.
- Raw log records (append-only JSONL): the identity fields above, `status`
  (`success`, `parse_error` or `api_error`), `raw_response`, `parsed_label`.
- Each planned slot ends in exactly one state: `valid_label`, `terminal_invalid`,
  `technical_failure` or `planned_unobserved`. Duplicates, records outside the plan,
  identity or hash mismatches, remediation records and labels that the strict parser
  does not reproduce are integrity errors, collected in full and raised.
- An `empirical` binding is refused unless the caller passes `allow_empirical=True`; no
  command in this package does.

## Method status

Implemented and tested on synthetic data: the input adapter, the procedure registry,
aggregation, samples, scores, comparators and margins, the framework bootstrap,
robustness checks, framework quantities and Tables 3.4A/B, the Firth adapter and
diagnostics, H1, the H2 core, the H3 point contrast, H4, E1 and the report layer.

Open or proposed (see the reviewer guide and the register):

| Item | Decision | Status in the code |
| --- | --- | --- |
| H3 inference procedure | D-H3-02 | Entry exists, refuses to run |
| H2 temporal sensitivity; appendix bootstrap and temporal Holm family; P-S ANOVA | D-H2-02, D-H2-03, D-H2-05 | Entries exist, refuse to run |
| Policy for an incomplete H2 Holm family | D-H2-04 | Family reported incomplete; no adjusted p-values |
| Firth convergence under the specified controls | D-FIRTH-03 | Fits that do not certify are reported as failed |
| HUMAN without a usable profile interval | D-FIRTH-05 | Stricter working rule, both readings recorded |
| Composition of the Table 3.4A/B rows | D-FW-04 | Proposed working rule |
| Chronology of data exposure | D-CHRON-01 | Documentation only |

None of these is resolved in code.

## What a reviewer can and cannot reproduce

Can, without reading the starting data:
- install the package and run the full synthetic suite and the data-free Chapter 3
  tests;
- check every rule in the specification against the code and its tests;
- run the worked example and inspect the report structure, tiers and pending table;
- with R and logistf 1.26.1, run the adapter on synthetic designs and see the
  convergence behaviour recorded under D-FIRTH-03.

Cannot:
- reproduce any empirical result of the thesis: no outputs or results are included and
  no empirical run has been made under this specification;
- check the empirical input binding (which collection supplies which model is itself
  open, D-IO-02);
- run the rest of the historical (pre-v2) test suite, which reads the private data and
  is not part of this package (only the six data-free Chapter 3 modules are included);
- launch a live Chapter 3 run from this package: no execution contract is included, and
  a contract binds the exact files it authorises by SHA-256.

## License

See `LICENSE`.

## Chapter 3: annotation plan and the code that launches the calls

The package holds the complete Chapter 3 plan: the protocol files, the experiment
definitions for the pilots and the full collections of all three models, the provider
routes, the code that builds a task manifest and executes it, and the Chapter 3 tests
that run without data (decisions D-EXPORT-01 and D-EXPORT-03). It holds no evidence that a
run happened or how it went.

**Reviewer-facing derived copies.** Twenty-one of these files originally also recorded
observations. They are included as derived copies (decision D-EXPORT-02): the observed
fields (outcomes of probes, smokes and pilots, token counts, real costs, real-run dates,
corrections about earlier reports, paths under `runs/`) are removed and every settings
field is unchanged. Each JSON copy starts with a `review_redaction` field that lists the
removed paths; the script copy starts with a comment that lists the changed lines. Hashes
recorded inside a copy (for example `supersedes.file_sha256`) refer to the original files,
which are not distributed. The copies were produced by
`python/scripts/chapter4_v2_redact_for_review.py`, which names paths and line numbers
only and runs where the originals are (not in this package). The cost estimator
(`chapter3_estimate_cost.py`) is **not** included: its default calibration constants are
observed values, so it cannot be redacted without changing what it computes.

- **Rubric:** `config/rubrics/societal_benefit_v1.json`: the construct definition,
  10 operational rules, 3 anchor examples taken from the Few-Shot prompt of Carlson and
  Burbano (2026, Table 3), and 4 removed rules kept with the status `non_operational`.
- **Label contract:** `config/labels/societal_benefit_labels_v1.json`: labels `0` and
  `1`; a completion is valid only if it is exactly `0` or `1` after stripping
  whitespace. A `parse_error` consumes the planned sample slot and is never retried
  automatically; a technical failure (no completion received) may be retried on the
  same slot.
- **Camuffo-type variance-aware prompts:** `config/prompts/camuffo_societal_benefit_P3_v1.json`:
  3 prompt variants (`base`, `paraphrase_1`, `paraphrase_2`) x 3 samples x 3 models,
  a shared system prompt rendered in two label orders, `"10"` (the rule for label 1
  first) and `"01"` (the rule for label 0 first), counterbalanced per cell
  (item x model x template), and a delimiter that marks the campaign text as content
  to classify, not instructions.
- **Carlson published baseline prompts:** `config/prompts/carlson_table3_v1.json`:
  the seven strategies of Carlson and Burbano (2026, Table 3): Zero-shot, Few-Shot,
  Role-Based, Chain of Thought (CoT), Self-Consistency, Tree of Thought (ToT) and
  Reflection on Search Trees (RoT) (template IDs `cb_t3_zero_shot` ... `cb_t3_rot`).
  The paper itself is not redistributed.
- **Experiment definitions** (`config/experiments/`): v1 (three-model design), v2 and
  v3_hf_full (DeepSeek V4 Pro through the Hugging Face router), v4 and v5 (first-party
  smokes), v6 and v7 (GPT-5.6 Terra pilot and full collection), v8 and v9 (Claude
  Sonnet 5 pilot and full collection), and `config/chapter3_experiment.json` (the earlier
  single-arm design that `chapter3_design.py` and `chapter3_execute.py` read by default).
  Models: `gpt-5.6-terra` (OpenAI), `claude-sonnet-5` (Anthropic) and DeepSeek V4 Pro
  (`deepseek/deepseek-v4-pro-0813`, or `deepseek-ai/DeepSeek-V4-Pro-0813:deepinfra` on
  the Hugging Face route). The pilot scopes keep their item lists: the 12 pilot items,
  recorded as selected by the deterministic, label-blind hash rule, and the one smoke item.
- **Routes** (`config/routes/`): the DeepSeek Hugging Face route (v1-v3), the Anthropic
  route for Claude Sonnet 5 (v1-v4) and the OpenAI route for GPT-5.6 Terra (v1-v4), with
  the request settings on the wire, documented capabilities, tariff snapshots and the
  local cost formula.
- **Code** (`python/src/chapter3/`): `catalog.py` (validates the definition files
  against each other and builds the prompt catalogue; fails closed on unapproved files
  and drifted hashes), `manifest.py` (two-arm task manifest; label-blind, deterministic
  item selection; refuses to read the real dataset until every gate is clear),
  `providers.py`, `first_party.py`, `huggingface.py` (provider adapters with injected
  clients; tariff snapshots; documented route capabilities), `execution.py` and
  `runner_two_arm.py` (append-only JSONL log, dry run by default, hard call and cost
  caps for a live run, resume keyed on `task_id`).
- **Scripts:** `python/scripts/chapter3_execute_two_arm.py` (derived copy; verifies,
  plans and, only under a frozen execution contract, executes a two-arm manifest; a dry
  run writes nothing), `chapter3_design.py` and `chapter3_execute.py` (the earlier
  single-arm path; `chapter3_execute.py` is a dry run unless `--live` is given together
  with `--max-calls` and `--max-usd`, and switches SDK retries off). None of these
  scripts was run against the starting data in preparing this package. A live call
  needs credentials and, for the two-arm script, an execution contract, neither of which
  is included.

The provider SDKs (`openai`, `anthropic`) are imported only inside the live-call
path, so neither the tests nor an import of any module needs them.

Run the Chapter 3 tests (no credentials, no network; they do not read `data/`):

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s python/tests/chapter3 -v
```

The folder holds only the six selected modules and their helper `_fakes.py`. One
test, `test_catalog.ExperimentAndGateTests.test_reference_hashes_match_the_files_on_disk`,
is reported as **skipped** here because it also hashes the source paper; the next test
checks the hashes of the rubric, label and prompt files.

## Starting data

`data/` holds the starting inputs that no run generated (decision D-EXPORT-03), each
listed by name in the allowlist and pinned by SHA-256 in the export builder and in
`EXPORT_MANIFEST.json`:

| File | What it is |
| --- | --- |
| `data/test_sample.csv` | The benchmark dataset the experiment definitions point to (`dataset.path`) |
| `data/prompt_variations.csv` | Prompt source file that the Carlson prompt configuration and `config/chapter3_experiment.json` refer to |
| `data/prompt_creation_template.txt` | Prompt source file that the Carlson prompt configuration refers to |

Not included: the Carlson and Burbano paper (`docs/sources/`) and any other third-party
file that is not redistributed, the data folder's own README, and everything a run
produced (manifests, logs, reports). **Provenance and redistribution licence of these
files are to be confirmed by the author, and the repository must stay private until
then.** The Chapter 4 test guard refuses to open anything under `data/`, and no Chapter 3
test opens it.
