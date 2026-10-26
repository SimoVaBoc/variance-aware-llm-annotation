"""Chapter 4 consolidated analysis, specification version 2 (Revision 2 of 2026-10-25).

The modules below implement the confirmed plan recorded in
``config/analysis/chapter4_analysis_spec_v2.json`` and the decision register
next to it. Importing this package performs no I/O and starts no analysis:
every computation is an explicit function call, and real data enter only
through an explicit data root (see :mod:`.io_boundary`).

Module boundaries follow the implementation brief: specification, decision
register, provenance, the task-level input adapter and the I/O boundary come
first; procedures, scores, framework, Firth and the focused analyses follow in
their own modules.
"""
