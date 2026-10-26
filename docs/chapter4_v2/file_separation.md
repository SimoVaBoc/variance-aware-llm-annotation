# File separation: private material and the review package

Status: written in Step 1, updated in Step 6 (2026-10-26) with the final allowlist and
after the review-export fixes (2026-10-26, D-EXPORT-01 to D-EXPORT-03).

## Private archive

Empirical material lives in a sibling private folder, outside this repository:

```
../Codice_tesi_private/
  data/            byte copy of the repository's data/ (4 files)
  runs/            byte copy of the repository's runs/ (198 files)
  preservation/    SHA-256 inventories and the preservation manifest
```

The copy was made with `python/scripts/chapter4_v2_preserve_private.py copy` and
verified file by file (path, size, SHA-256) against an inventory taken before
any edit. The originals in `data/` and `runs/` were not moved or deleted, and no
record was opened except to hash its bytes. Re-check either tree at any time:

```powershell
python python/scripts/chapter4_v2_preserve_private.py verify `
    --root ..\Codice_tesi_private `
    --inventory ..\Codice_tesi_private\preservation\<inventory>.tsv
```

## This working repository

This Git repository is a **local working history only**. Its baseline commit
holds the historical tree, including documents, tests and `CLAUDE.md` that
embed empirical values. It must never be shared or pushed. `data/`, `runs/`,
`.venv/`, caches, credentials-like names and archives are excluded through the
local `.git/info/exclude`; the project `.gitignore` is unchanged.

## Analysis inputs

New analysis code reads private files only through an explicit data root and an
input binding kept outside version control (see
`python/src/chapter3/chapter4_v2/io_boundary.py`). It never builds the primary
analysis from older aggregate or report outputs. An empirical binding is
refused unless the caller authorises it explicitly; nothing in the current
stage does.

## Allowlist of the review package (Step 6)

The review package is a separate, clean export built by
`python/scripts/chapter4_v2_build_review_export.py` from the explicit, file-by-file
allowlist `docs/chapter4_v2/review_export_allowlist.json`, never from this history.
It holds:

- the new package `python/src/chapter3/chapter4_v2/` (including the R adapter), its
  synthetic tests `python/tests/chapter4_v2/` and the `chapter4_v2_*` scripts;
- the earlier modules the new code imports (the static import closure):
  `python/src/__init__.py`, `python/src/chapter3/__init__.py`, `aggregation`, `analysis`,
  `bootstrap`, `catalog`, `design`, `execution`, `first_party`, `hierarchy`,
  `huggingface`, `metrics`, `providers`, `results`;
- the specification and the decision register in `config/analysis/`;
- `docs/chapter4_v2/` (register, reviewer guide, this note, test separation, the
  allowlist), a new `README.md`, `.gitignore` and `requirements-review.txt` written for
  the export, and the original `LICENSE`;
- since the review-export fix (D-EXPORT-01): the Chapter 3 rubric, label contract and
  both prompt files, experiment definitions v1 and v3_hf_full, the DeepSeek Hugging
  Face route v1, `manifest.py`, `runner_two_arm.py`, `chapter3_design.py`,
  `chapter3_execute.py` and the six data-free Chapter 3 test modules with `_fakes.py`;
- since D-EXPORT-03: reviewer-facing derived copies of the twenty-one Chapter 3 files
  that record observations (`config/chapter3_experiment.json`, experiment definitions
  v2-v9, every route record, `chapter3_execute_two_arm.py`); experiment v1 and the
  protocol files needed no change and are exported as they are. They are written
  by `python/scripts/chapter4_v2_redact_for_review.py` into
  `docs/chapter4_v2/export/redacted/` and exported at the original paths; the frozen
  originals are untouched and refused as export sources. `chapter3_estimate_cost.py`
  stays out (D-EXPORT-02);
- since D-EXPORT-03: the starting data `data/test_sample.csv`,
  `data/prompt_variations.csv` and `data/prompt_creation_template.txt`, each an explicit
  allowlist entry. They are not tracked in this working history (`data/` stays in
  `.git/info/exclude`); the export builder pins their SHA-256 and refuses every other
  path under `data/`. `data/README.md` is not included. Provenance and redistribution
  licence are to be confirmed by the author; the review repository stays private until
  then.

`AI_disclosure.md` is not in the allowlist and is added only if the author says so.
`test_review_export.py` keeps the allowlist complete for the new code and closed to
private material.

Local paths and identity:

- `local_paths.json` (repository root) holds the local `Rscript` path. It is
  untracked and ignored through `.git/info/exclude`; the export's own
  `.gitignore` must list it too.
- Among tracked files, only the historical `AI_disclosure.md` contains the local
  user name or an absolute user path (checked by pattern, without reading it
  further). None of the new Chapter 4 v2 files does; `test_hygiene.py` keeps it so.
- Diagnostic scripts for D-FIRTH-03 live outside the repository and are not part
  of any export.

Excluded by default: everything under `data/` except the three starting inputs,
`runs/`, `.venv/`, `CLAUDE.md`, the historical `README.md` and `docs/` files,
`docs/sources/` (third-party paper), the rest of the historical test suite, the other
historical scripts, `config/execution/` (execution contracts), the frozen originals of
the redacted Chapter 3 files, `chapter3_estimate_cost.py`, `requirements*.txt` of the
working copy, and the original archives.
