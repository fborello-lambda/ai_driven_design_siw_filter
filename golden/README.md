# Golden designs

Curated, validated design constants and their measured S-parameters — the
values worth never losing, as opposed to `output/` (gitignored, regenerable
scratch). Only designs that actually meet or represent a real, reproducible
milestone go here; not every optimizer run.

## Layout

```
golden/<topology>_N<order>/<stem>.json          <- params + spec + summary metrics + provenance
golden/<topology>_N<order>/<stem>.s11s21.json   <- standalone {f_ghz, s11_db, s21_db} arrays
```

The two files for one design share the **identical stem** — differing only by
the `.s11s21.json` suffix — so they are trivially paired by filename, both by
eye and by `glob(stem + "*")` in a script.

## Naming convention

`<stem>` is every geometry parameter, name immediately followed by its value
(mm), underscore-joined in the same order the CLI prints them
(`siw layout --topology ... ` / `params: {...}`), then a launch-model tag:

```
a57.21_wiris15.26_xiris28.68_ywall8.62_wext16.31_sma_taoglas.json
  a=57.21  w_iris=15.26  x_iris=28.68  y_wall=8.62  w_ext=16.31   launch=sma_taoglas
```

**Launch tag — be precise, this distinction is load-bearing** (a mismatch
here is exactly the kind of bug this project already hit once):

- `sma_taoglas` — real Taoglas SMA (`with_sma=True`) + its discrete ground
  pads and stitching vias (`gnd_stitch=True`), but **pad-only**: no
  impedance-matched gap (`cpwg_gap_mm=None`).
- `cpwg_taoglas` — the above **plus** the real gap-matched CPWG launch
  (`cpwg_gap_mm=0.2512` etc, solved 50Ω — `docs/archive/TUNING_PLAN_2026-08-29.md` (tag docs-archive-2026-09-29)
  sec 2). Only use this tag when the run actually passed those `cpwg_*`
  kwargs. Both topologies default to this since 2026-09-02; dual-mode runs
  from before then used the pad-only launch (kept in git tag
  `docs-archive-2026-09-29`).

Append a free-text suffix before the extension for a variant of the same
geometry (e.g. `..._cpwg_taoglas_broadband.json` for a 0–8GHz sweep instead
of the narrowband confirm).

## Updating a golden entry

1. Reproduce it through the CLI (`siw compare-baselines`, `siw synth-design`,
   or `siw sweep` — never a one-off script; see CLAUDE.md).
2. If the new run's params or metrics differ from what's stored, overwrite
   the JSON pair — don't hand-edit numbers.
3. Update the `provenance` block (`git_commit_when_saved`, `saved` date,
   `reproduce_with` command) and, if the design itself changed, `CLAUDE.md`'s
   "Golden designs" pointer.

## Current entries

| Folder | What |
|---|---|
| `cascade_N3/l_cav133.94_…_cpwg_taoglas` | **the fabricated board** (end cavities trimmed −0.3 mm, 2026-09-23) |
| `cascade_N3/l_cav134.24_…` | the pre-trim golden it supersedes (+ 0–8 GHz broadband check) |
| `cascade_N4/` | N=4 cascade, parked comparison point |
| `dualmode_N2/a57.16_…_cpwg_taoglas` | dual-mode N=2 under the CPWG launch — documented negative result |
