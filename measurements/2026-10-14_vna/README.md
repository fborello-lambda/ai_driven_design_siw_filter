# VNA measurements of the fabricated board — 2026-10-14

Fabricated cascade N=3 filter (`golden/cascade_N3/l_cav133.94_…`), JLCPCB,
Rogers RO4350B 0.76 mm, ENIG finish, no soldermask. Measured with a Keysight
FieldFox **N9917A** (18 GHz) between 100 MHz and 5 GHz, 10 001 points, IF
bandwidth 10 kHz, source power −15 dBm.

> The instrument's own clock (stored in each file header) reads 15 October 2026;
> the session is filed under 14 October as taken. Headers are unmodified.

## Calibration

The instrument was calibrated at the ends of the two test cables with the
3.5 mm mechanical kit (85033D/E), **full two-port SOLR (unknown thru), isolation
omitted** (photo `photos/vna_cal_setup.jpg`). In the `.s2p` headers,
`Correction: …(ON U)` means the calibration is applied, `…(Rdy)` means it is
stored but not applied (raw data).

## Files

| File | State | Original name |
|---|---|---|
| `dut_soldered_calibrated.s2p` | connectors soldered, instrument-calibrated | `File_SC` |
| `dut_soldered_uncalibrated.s2p` | connectors soldered, raw | `File_SU` |
| `dut_unsoldered_calibrated.s2p` | connectors seated, not soldered, calibrated | `File_UC` |
| `dut_unsoldered_uncalibrated.s2p` | connectors seated, not soldered, raw | `File_UU` |
| `check_thru_calibrated.s2p` | thru measured after the instrument calibration (verification) | `calibration_thru` |
| `raw_standards/port1_{open,short,match}.s2p` | raw standards on port 1 (use S11) | `File_1O/1S/1M` |
| `raw_standards/port2_{open,short,match}.s2p` | raw standards on port 2 (use S22) | `File_2O/2S/2M` |
| `raw_standards/thru.s2p` | raw thru (adapter of unknown length) | `File_T` |
| `processed/*.s2p` | software-calibrated DUT files, written by `siw measure --paper` | — |
| `photos/` | setup photos, rotated/downscaled, metadata stripped | — |

## Use

```bash
siw measure              # software calibration + figures of merit + comparison table
siw measure --fit        # also the (experimental) coupling-matrix fit and loss sweep
siw measure --paper      # refresh the tables/figures used in docs/paper/
```

`siw measure` re-calibrates the raw DUT files from the raw standards (SOL on
each port, reciprocal unknown thru, `scikit-rf`) and checks the result against
the instrument-calibrated files: mean |ΔΓ| 0.03 (S11) / 0.04 (S22) and 0.17 dB
in S21 over 2.6–3.2 GHz. A passive thru cannot show gain, but the calibrated thru
reads +0.18 dB (instrument) and +0.26 dB (software), so S21 carries about
0.3 dB of uncertainty.

## Caveats

* One board, one session. The photographed instrument screens
  (`photos/vna_screen.jpg`, S21 −2.34 dB / S11 −20.6 dB at 2.8706 GHz) were taken
  about 30 minutes before these files and show a different state; they are kept
  as documentation only and no number in the papers comes from them.
* The calibration plane is the SMA connector face. No de-embedding of the
  connectors or launch was done.
