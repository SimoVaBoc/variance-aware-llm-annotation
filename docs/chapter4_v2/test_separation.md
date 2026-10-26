# Test separation for the Chapter 4 v2 implementation

Status: Step 1 of the implementation, 2026-10-26.

## Public synthetic suite

`python/tests/chapter4_v2/` is the public test suite of the new analysis. It
uses invented fixtures only (`fixtures.py`: items `SYN1`, `SYN2`, ...,
placeholder texts, digests of fixture identifiers).

Every module imports `_guard.py` first. The guard installs a process-wide audit
hook that refuses to open or list any path under the repository's `data/` or
`runs/` trees, or under a folder named `Codice_tesi_private`. It refuses on the
path alone, before the operating system is asked for the file, so a blocked
file is never read. Each test also blocks the socket calls that open a network
connection.

Run it from the repository root:

```powershell
python -m unittest discover -s python/tests/chapter4_v2 -v
```

## Historical suite (`python/tests/chapter3/`)

The historical suite is **private and historical**. It is not run in the
working repository. Since the review-export fix (decision D-EXPORT-01) six of
its modules, `test_catalog`, `test_hierarchy`, `test_results`, `test_providers`,
`test_manifest` and `test_runner_row_settings`, with their helper `_fakes.py`, are
part of the review package: they use invented fixtures and the protocol files, and
were run only in clean copies without `runs/` or network, first without `data/` and,
since D-EXPORT-03, with the starting data present under an audit hook that refuses any
open of a path under `data/` (none was attempted). In `test_manifest`
the only call that would read the dataset is refused by its gates before any read.
`test_catalog`'s check of every reference hash is skipped where the third-party
source paper is absent; a separate test checks the four protocol files. The rest
of the suite stays out of the package:

- many of its modules read `data/` or `runs/` directly;
- several assert observed empirical values (counts, coefficients) as expected
  results;
- `test_regression.py` fits the historical MLE model on the real benchmark.

The table below is a **static, heuristic** classification from the source text
(path literals and loader calls). No historical test was executed to produce
it, so it is unverified.

| Class | Modules |
| --- | --- |
| Reads `data/` or `runs/` (directly, or through loaders such as `load_items` or `generate` on the project root) | `test_chapter4_rq_map` (see below), `test_chapter4_bootstrap`, `test_chapter4_report`, `test_design`, `test_execute_two_arm_cli`, `test_execution`, `test_first_party_smoke`, `test_first_party_smoke_v2`, `test_hf_consolidation`, `test_legacy_manifest_guard`, `test_providers_huggingface`, `test_regression`, `test_sonnet_full`, `test_sonnet_pilot`, `test_sonnet_smoke_v2`, `test_table3_provenance`, `test_terra_full`, `test_terra_pilot`, `test_three_model_consolidation`, `test_two_arm_execution`, `test_variance_decomposition` |
| Reads frozen configurations, documents or source files, not `data/` or `runs/` by its literals | `test_catalog`, `test_hierarchy`, `test_execute_cli`; `test_manifest` (moved here after Step 6: it calls `generate` on the project root, but each definitive call is refused by a gate before the dataset is read) |
| No repository file literal found | `test_aggregation`, `test_analysis`, `test_metrics`, `test_providers`, `test_results`, `test_runner_row_settings` |

The second and third classes may still reach private files indirectly, for
example through a CLI that reads its default paths. A later run of any
historical module should therefore happen only under the same guard as the
public suite, so that an indirect read fails instead of happening. That run is
a separate decision and is not part of this step.

## Tests that need R

`test_firth_r.py` exercises the R logistf adapter. It runs only when `Rscript`
is found (environment variable `CHAPTER4_V2_RSCRIPT`, a local untracked
`local_paths.json`, or `PATH`) and reports logistf 1.26.1. Otherwise every test
in it is reported as **skipped**, with the reason, and never counted as passed.
All other Firth logic (design, pre-fit checks, separation, judging adapter
outputs, distances, H4, E1) is tested without R.

## Obsolete historical assertions (updated in Step 4)

Three assertions in `test_chapter4_rq_map.py` described the earlier plan: Firth
recorded as an open decision, Firth absent from `regression.py`, and the Carlson
comparator recorded as open. Their substance still holds for the historical
files they read, which stay unedited, so nothing was removed. The tests were
renamed and documented as tests of the historical record, each linked to the
decision that supersedes it:

| Test (new name) | Superseded by |
| --- | --- |
| `test_historical_v1_map_records_firth_as_open` | D-FIRTH-01 (H-FIRTH-01) |
| `test_historical_mle_module_stays_free_of_firth` | D-FIRTH-01, D-FIRTH-02 (H-MLE-01) |
| `test_historical_v1_map_records_the_carlson_comparator_as_open` | D-CMP-01 (H-CMP-01) |

What each renamed test asserts:

- `test_historical_v1_map_records_firth_as_open` reads the historical document
  `config/analysis/chapter4_rq_analysis_map_v1.json` (record
  `rq3_firth_parallel_column`);
- `test_historical_mle_module_stays_free_of_firth` reads historical code,
  `python/src/chapter3/regression.py`, and asserts it defines no Firth function;
- `test_historical_v1_map_records_the_carlson_comparator_as_open` reads the same
  historical document (record `rq2_carlson_comparator_definition`).

No positive assertion that the new Firth path exists is added to this historical
file: the public suite already asserts it (`test_hygiene`, `test_imports`, and the
Firth tests import and exercise `chapter4_v2.firth` and its R adapter).

The file was **not run**. Reading its source (Step 4 addendum) shows that it is
data-dependent: `test_every_referenced_path_exists` checks the existence of every
input and output artifact the v1 map names, and
`test_json_pointers_resolve_in_the_artefact_they_name` opens the output-artifact
JSON files, which are historical empirical outputs. It also asserts an observed
coefficient in `test_the_benchmark_coefficient_is_recorded_with_its_diagnostics`.
It is therefore classified with the data-dependent modules above and left
unrun; the edit is verified only by parsing the file.
