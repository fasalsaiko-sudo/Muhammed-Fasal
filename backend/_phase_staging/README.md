# `_phase_staging/` — parked Phase 4–8 code (NOT active, NOT verified)

This directory holds code generated during the earlier one-pass implementation
that the project owner explicitly asked to **stop and replace with verified
phases**. It was moved here rather than deleted so nothing is lost, but it is
**outside the import path**: nothing in `app/` imports it, so the running
application and the test suite never touch it.

## Status

| Group | Contents | Intended phase | State |
| --- | --- | --- | --- |
| `routes/` | auth, projects, certifications, experience, skills, writeups, cv, media, profile, settings, dashboard, backup, dependencies | 5, 7, 8 | unverified draft |
| `services/` | drive, github_oauth, auth/session, audit, versioning, backup, orphan detection | 4, 5, 8 | unverified draft |
| `middleware/` | authentication, authorization | 5 | unverified draft |
| `schemas/` | request/response models for the above | 7, 8 | unverified draft |
| `tests/` | 5 modules, 16 previously failing tests | 4–8 | **failing — not fixed** |

## Why it is excluded from Git

The pull request for the current phase contains only code that has actually
been executed by a passing test. Committing these files would reintroduce the
large speculative change set that was rejected, and their tests do not pass.
They are re-introduced one module at a time in Phases 4–8, each behind its own
verified tests.

## How to reactivate a module

1. Move the module back under `app/` (e.g. `app/services/drive.py`).
2. Register its router in `app/main.py` behind the phase's feature flag.
3. Move the matching tests into `tests/` and make them pass on **both** SQLite
   and PostgreSQL before considering the module done.
