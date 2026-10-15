"""Bench measurements -> software calibration -> comparison with simulation.

Closes the design loop (spec -> synthesis -> EM -> fab -> *measurement*):

  * loads a VNA dataset (default: ``measurements/2026-10-14_vna/``): the board
    measured with the instrument's own calibration (soldered / unsoldered
    connectors) and without it, plus the raw open/short/match/thru standards
    measured at the same calibration plane;
  * re-calibrates the uncalibrated measurements in software (one-port SOL on
    each port + reciprocal *unknown thru*, skrf ``UnknownThru``) and checks the
    result against the instrument-calibrated files;
  * extracts the filter figures of merit with ONE definition for every source
    (spec, Palace, CST, VNA) and renders the comparison table + figures;
  * optionally fits a lossy coupling matrix to the measurement.

Run ``siw measure`` (or ``uv run python -m siwfilter.measure``).
"""
from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass, field

import numpy as np

from .config import FilterSpec, data_path, out_data, out_img, out_s2p  # noqa: F401  (out_data re-exported for the CLI)

DEFAULT_DATASET = data_path("measurements", "2026-10-14_vna")
_GOLDEN_STEM = ("golden/cascade_N3/l_cav133.94_l_cav235.5_l_taper15.74_w_ext13.96_"
                "w_iris14.42_w_ms1.66_cpwg_taoglas")
DEFAULT_PALACE = data_path(_GOLDEN_STEM + ".s11s21.json")
DEFAULT_PALACE_BB = data_path("golden/cascade_N3/l_cav134.24_l_cav235.5_l_taper15.74_"
                              "w_ext13.96_w_iris14.42_w_ms1.66_cpwg_taoglas_broadband.s11s21.json")
DEFAULT_CST = data_path("golden/cascade_N3/cst/cst_fd_fixed_pretrim_2026-09-06.s2p")
DEFAULT_CST_BB = data_path("golden/cascade_N3/cst/cst_fd_broadband_0_8ghz_pretrim_2026-09-06.s2p")
LAUNCH_SUMMARY = data_path("docs", "launch_comparison", "summary.json")

REJECT_FREQS_GHZ = (2.45, 3.5)       # Wi-Fi 2.4 GHz, 5G n78
SPUR_RANGE_GHZ = (3.6, 5.0)          # common to every source (VNA stops at 5 GHz)
FIT_RANGE_GHZ = (2.6, 3.2)

# dataset file name -> short key
DUT_FILES = {
    "SC": "dut_soldered_calibrated.s2p",
    "SU": "dut_soldered_uncalibrated.s2p",
    "UC": "dut_unsoldered_calibrated.s2p",
    "UU": "dut_unsoldered_uncalibrated.s2p",
}
STD_FILES = {
    "p1_open": "port1_open.s2p", "p1_short": "port1_short.s2p", "p1_match": "port1_match.s2p",
    "p2_open": "port2_open.s2p", "p2_short": "port2_short.s2p", "p2_match": "port2_match.s2p",
    "thru": "thru.s2p",
}
CHECK_THRU = "check_thru_calibrated.s2p"


# --------------------------------------------------------------------------
# data containers
# --------------------------------------------------------------------------
@dataclass
class Curve:
    """One source of S-parameters (|S| in dB; S22 only for measurements)."""
    name: str
    f_ghz: np.ndarray
    s11_db: np.ndarray
    s21_db: np.ndarray
    s22_db: np.ndarray | None = None
    kind: str = "sim"                       # "sim" | "vna" | "swcal"
    note: str = ""
    net: object = field(default=None, repr=False)   # skrf Network when available


def _db(x) -> np.ndarray:
    return 20 * np.log10(np.maximum(np.abs(x), 1e-12))


def curve_from_network(name: str, net, kind: str, note: str = "") -> Curve:
    f = np.asarray(net.f) / 1e9
    return Curve(name, f, _db(net.s[:, 0, 0]), _db(net.s[:, 1, 0]), _db(net.s[:, 1, 1]),
                 kind, note, net)


def curve_from_golden(name: str, path: str, note: str = "") -> Curve:
    d = json.load(open(path))
    return Curve(name, np.asarray(d["f_ghz"], float), np.asarray(d["s11_db"], float),
                 np.asarray(d["s21_db"], float), None, "sim", note)


def curve_from_s2p(name: str, path: str, kind: str = "sim", note: str = "") -> Curve:
    import skrf as rf
    return curve_from_network(name, rf.Network(path), kind, note)


# --------------------------------------------------------------------------
# dataset + software calibration
# --------------------------------------------------------------------------
@dataclass
class Dataset:
    root: str
    dut: dict
    std: dict
    check_thru: object | None


def load_dataset(root: str = DEFAULT_DATASET) -> Dataset:
    import skrf as rf
    root = os.path.abspath(root)
    dut = {k: rf.Network(os.path.join(root, v)) for k, v in DUT_FILES.items()
           if os.path.exists(os.path.join(root, v))}
    std = {k: rf.Network(os.path.join(root, "raw_standards", v)) for k, v in STD_FILES.items()
           if os.path.exists(os.path.join(root, "raw_standards", v))}
    ct = os.path.join(root, CHECK_THRU)
    return Dataset(root, dut, std, rf.Network(ct) if os.path.exists(ct) else None)


def _reflection_standard(kind: str, f_hz: np.ndarray, model: str) -> np.ndarray:
    """Reflection coefficient of an open/short/match standard.

    ``ideal``: Gamma = +1 / -1 / 0. ``nominal``: first-order 85033D/E-style model
    (offset delay + open fringing capacitance), i.e. the definitions the
    instrument was SET to. The physical standards of the 2026-10-14 session were a
    generic SMA short/open/load, so these definitions are an assumption shared by the
    instrument's calibration and ours: their agreement checks the implementation, not
    the standards. The values are typical ones, not read from the instrument.
    """
    n = len(f_hz)
    if kind == "match":
        return np.zeros(n, complex)
    if model == "ideal":
        return (np.ones(n) if kind == "open" else -np.ones(n)).astype(complex)
    w = 2 * np.pi * f_hz
    if kind == "short":
        return -np.exp(-2j * w * 31.785e-12)
    c = 49.43e-15 - 310.1e-27 * f_hz + 23.17e-36 * f_hz ** 2 - 0.1597e-45 * f_hz ** 3
    return (1 - 1j * w * c * 50) / (1 + 1j * w * c * 50) * np.exp(-2j * w * 29.243e-12)


class SoftwareCal:
    """SOL on each port + reciprocal unknown thru (Ferrero-Pisani), 8-term model.

    The instrument used SOLR with an unknown thru and "omit isolation", so
    isolation is not corrected here either.
    """

    def __init__(self, ds: Dataset, model: str = "nominal"):
        import skrf as rf
        from skrf.calibration import UnknownThru
        s = ds.std
        missing = [k for k in STD_FILES if k not in s]
        if missing:
            raise FileNotFoundError(f"missing calibration standards: {missing}")
        f = s["thru"].frequency
        z = np.zeros((len(f), 2, 2), complex)

        def two_port(g11, g22):
            n = rf.Network(frequency=f, s=z.copy())
            n.s[:, 0, 0], n.s[:, 1, 1] = g11, g22
            return n

        measured, ideals = [], []
        for kind in ("short", "open", "match"):
            measured.append(two_port(s[f"p1_{kind}"].s[:, 0, 0], s[f"p2_{kind}"].s[:, 1, 1]))
            g = _reflection_standard(kind, f.f, model)
            ideals.append(two_port(g, g))
        thru_ideal = rf.Network(frequency=f, s=np.tile(np.array([[0, 1], [1, 0]], complex),
                                                        (len(f), 1, 1)))
        measured.append(s["thru"])
        ideals.append(thru_ideal)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.cal = UnknownThru(measured=measured, ideals=ideals)
            self.cal.run()
        self.model = model

    def apply(self, net):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return self.cal.apply_cal(net)


def calibration_report(ds: Dataset, cal: SoftwareCal, spec: FilterSpec | None = None) -> dict:
    """How well does the software calibration reproduce the instrument's?

    Pairs: SU->SC and UU->UC (same board, same session, calibrated vs raw).
    """
    spec = spec or FilterSpec(N=3)
    out = {"model": cal.model, "pairs": {}}
    for raw_k, ref_k in (("SU", "SC"), ("UU", "UC")):
        if raw_k not in ds.dut or ref_k not in ds.dut:
            continue
        sw, ref = cal.apply(ds.dut[raw_k]), ds.dut[ref_k]
        f = ref.f / 1e9
        m = (f >= 2.6) & (f <= 3.2)
        d21 = _db(sw.s[m, 1, 0]) - _db(ref.s[m, 1, 0])
        dg11 = np.abs(sw.s[m, 0, 0] - ref.s[m, 0, 0])
        dg22 = np.abs(sw.s[m, 1, 1] - ref.s[m, 1, 1])
        out["pairs"][f"{raw_k}->{ref_k}"] = {
            "s21_mean_diff_db": float(d21.mean()), "s21_max_abs_diff_db": float(np.abs(d21).max()),
            "s11_mean_dgamma": float(dg11.mean()), "s22_mean_dgamma": float(dg22.mean()),
            "band_ghz": [2.6, 3.2]}
    if ds.check_thru is not None:
        t = ds.check_thru
        f = t.f / 1e9
        m = (f >= 2.6) & (f <= 3.2)
        sw_thru = cal.apply(ds.std["thru"])
        out["thru_check"] = {
            "instrument_s21_db_mean": float(_db(t.s[m, 1, 0]).mean()),
            "instrument_s11_db_max": float(_db(t.s[m, 0, 0]).max()),
            "software_s21_db_mean": float(_db(sw_thru.s[m, 1, 0]).mean()),
            "software_s11_db_max": float(_db(sw_thru.s[m, 0, 0]).max())}
    return out


# --------------------------------------------------------------------------
# figures of merit (one definition for every source)
# --------------------------------------------------------------------------
def _zeros(f, s_db, lo=2.6, hi=3.2, depth=-10.0, prom=3.0):
    from scipy.signal import find_peaks
    m = (f >= lo) & (f <= hi)
    pk, _ = find_peaks(-s_db[m], prominence=prom)
    return [(float(f[m][i]), float(s_db[m][i])) for i in pk if s_db[m][i] <= depth]


def cheb_3db_ratio(N: int, ripple_db: float) -> float:
    """-3 dB bandwidth / ripple bandwidth of an N-th order Chebyshev prototype
    (1.388 for N=3, 0.1 dB). The spec's FBW is the RIPPLE bandwidth; every
    measured BW in this module is the -3 dB one."""
    import math
    eps = math.sqrt(10 ** (ripple_db / 10) - 1)
    return math.cosh(math.acosh(math.sqrt(10 ** 0.3 - 1) / eps) / N)


def q_metrics(fc_ghz: float, bw_mhz: float, il_db: float, spec: FilterSpec) -> dict:
    """Loaded Q of the passband and the effective unloaded Q implied by its loss.

    ``q_loaded = fc / BW_-3dB``. ``qu_eff`` inverts the narrow-band Chebyshev
    loss estimate IL0 = 4.343 sum(g_i) / (FBW Qu) (Hong & Lancaster), where FBW
    is the RIPPLE bandwidth: the curve's -3 dB FBW divided by ``cheb_3db_ratio``.
    Checked on the ideal lossy prototype (Qu 270 -> 270, 180 -> 181). Every loss
    in the source (connector, launch, radiation, mismatch) is charged to the
    resonators, so it is an effective Qu, not the resonator's own."""
    from .synthesis import chebyshev_g
    if not bw_mhz or bw_mhz <= 0:
        return {"q_loaded": None, "qu_eff": None}
    g = chebyshev_g(spec.N, spec.ripple_db)
    fbw_ripple = bw_mhz / 1e3 / fc_ghz / cheb_3db_ratio(spec.N, spec.ripple_db)
    return {"q_loaded": fc_ghz * 1e3 / bw_mhz,
            "qu_eff": 4.343 * float(np.sum(g[1:spec.N + 1])) / (fbw_ripple * il_db) if il_db > 0 else None}


def q_theory(spec: FilterSpec) -> dict:
    """Design / material values the measured Q are compared with. ``q_loaded``
    is the -3 dB loaded Q of the ideal prototype (f0 / BW_-3dB); 1/FBW is the
    ripple-band value."""
    from .config import QC_COPPER_EST
    r = cheb_3db_ratio(spec.N, spec.ripple_db)
    qd = 1.0 / spec.substrate.tan_d
    return {"q_loaded": 1.0 / (spec.FBW * r), "q_loaded_ripple": 1.0 / spec.FBW,
            "bw3db_mhz": spec.FBW * r * spec.f0 / 1e6, "qu_dielectric": qd,
            "qu_dielectric_copper": 1.0 / (1.0 / qd + 1.0 / QC_COPPER_EST)}


def metrics(c: Curve, spec: FilterSpec | None = None) -> dict:
    """Figures of merit of one curve. dB values are S-parameter magnitudes
    (S21 = -insertion loss). In-band = f0 +/- FBW/2 of the SPEC, not of the
    curve's own centre, so a frequency shift is charged to the return loss."""
    from .optimize import band_edges
    spec = spec or FilterSpec(N=3)
    f = c.f_ghz
    b0, b1 = spec.f1 / 1e9, spec.f2 / 1e9
    band = (f >= b0) & (f <= b1)
    pass_m = (f >= 2.5) & (f <= 3.3)
    out: dict = {"name": c.name, "kind": c.kind, "note": c.note}
    if pass_m.sum() > 3 and f[pass_m].min() < b0 and f[pass_m].max() > b1:
        e = band_edges(f[pass_m], c.s21_db[pass_m])
        ip = int(np.argmax(c.s21_db[pass_m]))
        out.update(fc_ghz=e["fc_3db"], bw_mhz=e["bw"], fbw_pct=100 * e["bw"] / 1e3 / e["fc_3db"],
                   s21_peak_db=float(c.s21_db[pass_m][ip]), f_peak_ghz=float(f[pass_m][ip]),
                   s21_inband_worst_db=float(c.s21_db[band].min()),
                   s11_inband_worst_db=float(c.s11_db[band].max()),
                   s11_best_db=float(c.s11_db[pass_m].min()),
                   f_s11_best_ghz=float(f[pass_m][np.argmin(c.s11_db[pass_m])]),
                   n_s11_zeros=len(_zeros(f, c.s11_db)), band_truncated=bool(e["band_truncated"]),
                   f_lo_ghz=float(e["f_lo"]), f_hi_ghz=float(e["f_hi"]))
        out.update(q_metrics(out["fc_ghz"], out["bw_mhz"], -out["s21_peak_db"], spec))
        if c.s22_db is not None:
            out["s22_inband_worst_db"] = float(c.s22_db[band].max())
            out["s22_best_db"] = float(c.s22_db[pass_m].min())
    for fr in REJECT_FREQS_GHZ:
        if f.min() <= fr <= f.max():
            out[f"rej_{fr:g}_db"] = float(np.interp(fr, f, c.s21_db))
    sp = (f >= SPUR_RANGE_GHZ[0]) & (f <= SPUR_RANGE_GHZ[1])
    if sp.sum() > 3 and f.max() >= SPUR_RANGE_GHZ[1] - 0.05:
        i = int(np.argmax(c.s21_db[sp]))
        out["spur_db"], out["f_spur_ghz"] = float(c.s21_db[sp][i]), float(f[sp][i])
    return out


def _fill_from(m: dict, extra: Curve | None, spec) -> dict:
    """Take rejection/spur figures from a wideband sweep when the narrowband
    sweep of the same source does not reach them."""
    if extra is None:
        return m
    mx = metrics(extra, spec)
    for k in ("rej_2.45_db", "rej_3.5_db", "spur_db", "f_spur_ghz"):
        if k not in m and k in mx:
            m[k] = mx[k]
            m.setdefault("wideband_from", extra.name)
    return m


# --------------------------------------------------------------------------
# assembling the comparison
# --------------------------------------------------------------------------
def build_curves(ds: Dataset, cal: SoftwareCal, palace=DEFAULT_PALACE, palace_bb=DEFAULT_PALACE_BB,
                 cst=DEFAULT_CST, cst_bb=DEFAULT_CST_BB) -> dict[str, Curve]:
    c: dict[str, Curve] = {}
    if palace and os.path.exists(palace):
        c["palace"] = curve_from_golden("Palace", palace, "fine mesh, trimmed (fabricated) geometry")
    if palace_bb and os.path.exists(palace_bb):
        c["palace_bb"] = curve_from_golden("Palace 0-8 GHz", palace_bb, "pre-trim geometry")
    if cst and os.path.exists(cst):
        c["cst"] = curve_from_s2p("CST", cst, "sim", "FD solver, pre-trim geometry")
    if cst_bb and os.path.exists(cst_bb):
        c["cst_bb"] = curve_from_s2p("CST 0-8 GHz", cst_bb, "sim", "pre-trim geometry")
    for k, label in (("SC", "VNA soldered, cal."), ("UC", "VNA unsoldered, cal.")):
        if k in ds.dut:
            c[k] = curve_from_network(label, ds.dut[k], "vna", "instrument calibration")
    for raw_k, key, label in (("SU", "SW_S", "Software cal., soldered"),
                              ("UU", "SW_U", "Software cal., unsoldered")):
        if raw_k in ds.dut:
            c[key] = curve_from_network(label, cal.apply(ds.dut[raw_k]), "swcal",
                                        f"SOL + unknown thru, {cal.model} standards")
    for k, label in (("SU", "VNA soldered, uncal."), ("UU", "VNA unsoldered, uncal.")):
        if k in ds.dut:
            c["raw_" + k] = curve_from_network(label, ds.dut[k], "raw", "no correction")
    return c


def comparison_metrics(curves: dict[str, Curve], spec: FilterSpec | None = None) -> dict:
    spec = spec or FilterSpec(N=3)
    out = {}
    for key in ("palace", "cst", "SC", "UC", "SW_S", "SW_U"):
        if key in curves:
            m = metrics(curves[key], spec)
            if key == "palace":
                m = _fill_from(m, curves.get("palace_bb"), spec)
            elif key == "cst":
                m = _fill_from(m, curves.get("cst_bb"), spec)
            out[key] = m
    return out


SPEC_COLUMN = lambda spec: {  # noqa: E731
    "fc_ghz": spec.f0 / 1e9, "bw_mhz": spec.FBW * spec.f0 / 1e6, "fbw_pct": 100 * spec.FBW,
    "s11_inband_worst_db": -16.0, "q_loaded": q_theory(spec)["q_loaded"]}


# --------------------------------------------------------------------------
# table rendering
# --------------------------------------------------------------------------
LABELS = {
    "en": {
        "cols": ["Spec.", "CST", "Palace", "VNA SC", "VNA UC", "SW S", "SW U"],
        "rows": {
            "fc_ghz": "Centre frequency (GHz)", "bw_mhz": r"$-3$\,dB bandwidth (MHz)",
            "fbw_pct": "Fractional bandwidth (\\%)",
            "q_loaded": r"Loaded $Q_L = f_c/\mathrm{BW}$", "qu_eff": r"Effective $Q_u$ (from IL)",
            "s21_peak_db": r"Peak $S_{21}$ (dB)",
            "s21_inband_worst_db": r"Worst in-band $S_{21}$ (dB)",
            "s11_inband_worst_db": r"Worst in-band $S_{11}$ (dB)",
            "s22_inband_worst_db": r"Worst in-band $S_{22}$ (dB)",
            "s11_best_db": r"Best $S_{11}$ (dB @ GHz)", "n_s11_zeros": r"$S_{11}$ zeros $<-10$\,dB",
            "rej_2.45_db": r"$S_{21}$ at 2.45\,GHz (dB)", "rej_3.5_db": r"$S_{21}$ at 3.5\,GHz (dB)",
            "spur_db": r"Strongest spur (dB @ GHz)"},
        "caption": (r"Fabricated cascade N=3 filter: specification, simulation and measurement. "
                    r"Every column is processed with the same code. In-band is $2.870\pm1.4\%$\,GHz "
                    r"(the specified 5\,\% band). CST is the pre-trim geometry. Palace in-band figures "
                    r"are for the fabricated geometry; its $S_{21}$ at 2.45/3.5\,GHz and spur are from "
                    r"the pre-trim 0--8\,GHz sweep. The spur is the largest $S_{21}$ between 3.6 and 5.0\,GHz. "
                    r"Measured columns: VNA = instrument calibration, SW = software recalibration of the "
                    r"raw files (Sec.~\ref{sec:vna}); S = connectors soldered, U = unsoldered, C = calibrated. "
                    r"$Q_L$ and the effective $Q_u$ are defined in Sec.~\ref{sec:q}. The specified bandwidth "
                    r"is the 0.1\,dB ripple bandwidth; the specification $Q_L$ is that of the ideal prototype "
                    r"at $-3$\,dB (199\,MHz), not $1/\mathrm{FBW} = 20$."),
        "label": "tab:comparison"},
    "es": {
        "cols": ["Espec.", "CST", "Palace", "VNA SC", "VNA UC", "SW S", "SW U"],
        "rows": {
            "fc_ghz": "Frecuencia central (GHz)", "bw_mhz": r"Ancho de banda a $-3$\,dB (MHz)",
            "fbw_pct": "Ancho de banda fraccional (\\%)",
            "q_loaded": r"$Q$ cargado $Q_L = f_c/\mathrm{BW}$", "qu_eff": r"$Q_u$ efectivo (de la IL)",
            "s21_peak_db": r"$S_{21}$ pico (dB)",
            "s21_inband_worst_db": r"Peor $S_{21}$ en banda (dB)",
            "s11_inband_worst_db": r"Peor $S_{11}$ en banda (dB)",
            "s22_inband_worst_db": r"Peor $S_{22}$ en banda (dB)",
            "s11_best_db": r"Mejor $S_{11}$ (dB @ GHz)", "n_s11_zeros": r"Ceros de $S_{11}<-10$\,dB",
            "rej_2.45_db": r"$S_{21}$ en 2.45\,GHz (dB)", "rej_3.5_db": r"$S_{21}$ en 3.5\,GHz (dB)",
            "spur_db": r"Mayor espuria (dB @ GHz)"},
        "caption": (r"Filtro N=3 en cascada fabricado: especificación, simulación y medición. "
                    r"Todas las columnas se procesan con el mismo código. La banda es "
                    r"$2.870\pm1.4\%$\,GHz (la banda especificada del 5\,\%). CST corresponde a la "
                    r"geometría previa al recorte. Las cifras de Palace en banda son de la geometría "
                    r"fabricada; su $S_{21}$ en 2.45/3.5\,GHz y la espuria provienen del barrido de "
                    r"0--8\,GHz previo al recorte. La espuria es el mayor $S_{21}$ entre 3.6 y 5.0\,GHz. "
                    r"Columnas medidas: VNA = calibración del instrumento, SW = recalibración por software "
                    r"de los archivos sin calibrar (Sec.~\ref{sec:vna}); S = conectores soldados, "
                    r"U = sin soldar (\emph{unsoldered}), C = calibrado. $Q_L$ y $Q_u$ efectivo se "
                    r"definen en la Sec.~\ref{sec:q}. El ancho de banda especificado es el de rizado de "
                    r"0.1\,dB; el $Q_L$ de la especificación es el del prototipo ideal a $-3$\,dB (199\,MHz), "
                    r"no $1/\mathrm{FBW} = 20$."),
        "label": "tab:comparison"},
}

_COLS = ("spec", "cst", "palace", "SC", "UC", "SW_S", "SW_U")
_ROWS = ("fc_ghz", "bw_mhz", "fbw_pct", "q_loaded", "qu_eff", "s21_peak_db", "s21_inband_worst_db", "s11_inband_worst_db",
         "s22_inband_worst_db", "s11_best_db", "n_s11_zeros", "rej_2.45_db", "rej_3.5_db", "spur_db")


def _cell(key: str, m: dict | None) -> str:
    if m is None or key not in m:
        return "--"
    v = m[key]
    if key == "n_s11_zeros":
        return f"{int(v)}"
    if key == "fc_ghz":
        return f"{v:.3f}"
    if key == "bw_mhz":
        return f"{v:.0f}"
    if v is None:
        return "--"
    if key in ("fbw_pct", "q_loaded"):
        return f"{v:.1f}"
    if key == "qu_eff":
        return f"{v:.0f}"
    if key == "s11_best_db":
        return f"{v:.1f} @ {m['f_s11_best_ghz']:.3f}"
    if key == "spur_db":
        return f"{v:.1f} @ {m['f_spur_ghz']:.2f}"
    return f"{v:.1f}" if key.startswith(("rej", "s11", "s22")) else f"{v:.2f}"


def _tex_minus(cell: str) -> str:
    """Typeset negative numbers with a real minus sign ("-1.8 @ 2.88" -> "$-1.8$ @ 2.88")."""
    import re
    return re.sub(r"(?<![\w$])-(\d)", r"$-$\1", cell)


def comparison_table_latex(cm: dict, spec: FilterSpec, lang: str = "en") -> str:
    L = LABELS[lang]
    cols = {"spec": SPEC_COLUMN(spec), **cm}
    spec_cells = {"fc_ghz": f"{spec.f0 / 1e9:.3f}", "bw_mhz": f"{spec.FBW * spec.f0 / 1e6:.1f}",
                  "fbw_pct": f"{100 * spec.FBW:.1f}", "q_loaded": f"{q_theory(spec)['q_loaded']:.1f}",
                  "s11_inband_worst_db": "$\\le -16$"}
    lines = [r"\begin{table*}[t]", r"\centering", r"\footnotesize", r"\setlength{\tabcolsep}{4pt}",
             r"\caption{" + L["caption"] + "}", r"\label{" + L["label"] + "}",
             r"\begin{tabular}{l" + "c" * len(_COLS) + "}", r"\hline",
             " & ".join([""] + [f"\\textbf{{{h}}}" for h in L["cols"]]) + r" \\", r"\hline"]
    for r in _ROWS:
        cells = [spec_cells.get(r, "--") if c == "spec" else _tex_minus(_cell(r, cols.get(c)))
                 for c in _COLS]
        if all(x == "--" for x in cells):
            continue
        lines.append(" & ".join([L["rows"][r]] + cells) + r" \\")
    lines += [r"\hline", r"\end{tabular}", r"\end{table*}"]
    return "\n".join(lines)


def comparison_table_md(cm: dict, spec: FilterSpec, lang: str = "en") -> str:
    L = LABELS[lang]
    cols = {"spec": SPEC_COLUMN(spec), **cm}
    strip = lambda s: s.replace("\\mathrm{BW}", "BW").replace("\\,", " ").replace("$", "").replace("\\", "").replace("--", "-")  # noqa: E731
    out = ["| | " + " | ".join(L["cols"]) + " |", "|---|" + "---|" * len(_COLS)]
    for r in _ROWS:
        cells = [("--" if r not in ("fc_ghz", "bw_mhz", "fbw_pct", "q_loaded", "s11_inband_worst_db")
                  else {"fc_ghz": f"{spec.f0 / 1e9:.3f}", "bw_mhz": f"{spec.FBW * spec.f0 / 1e6:.1f}",
                        "fbw_pct": f"{100 * spec.FBW:.1f}", "q_loaded": f"{q_theory(spec)['q_loaded']:.1f}",
                        "s11_inband_worst_db": "<= -16"}[r])
                 if c == "spec" else _cell(r, cols.get(c)) for c in _COLS]
        if all(x == "--" for x in cells):
            continue
        out.append("| " + " | ".join([strip(L["rows"][r])] + cells) + " |")
    return "\n".join(out)


LAUNCH_LABELS = {
    "en": {"head": ["Launch", r"$f_c$ (GHz)", "BW (MHz)", r"$S_{21}$ (dB)", r"$S_{11}$ (dB)"],
           "rows": {"ms": "Microstrip, no conn.", "cpwg": "CPWG, no conn.",
                    "cpwg_sma": "CPWG + SMA, sim.", "meas": "CPWG + SMA, sold.",
                    "meas_u": "CPWG + SMA, unsold."},
           "caption": (r"Effect of the launch on the same filter geometry. The first three rows are "
                       r"Palace simulations (the ports of the two connector-less variants sit on the "
                       r"planar line and normalise to its own impedance, so they show the filter behind "
                       r"an ideally matched feed). The last two rows are the fabricated board (instrument calibration). $S_{21}$ is the "
                       r"peak and $S_{11}$ the worst value in the specified band."),
           "label": "tab:launch"},
    "es": {"head": ["Alimentación", r"$f_c$ (GHz)", "BW (MHz)", r"$S_{21}$ (dB)", r"$S_{11}$ (dB)"],
           "rows": {"ms": "Microstrip, sin conect.", "cpwg": "CPWG, sin conect.",
                    "cpwg_sma": "CPWG + SMA, sim.", "meas": "CPWG + SMA, sold.",
                    "meas_u": "CPWG + SMA, sin sold."},
           "caption": (r"Efecto de la alimentación sobre la misma geometría de filtro. Las tres "
                       r"primeras filas son simulaciones de Palace (los puertos de las dos variantes sin "
                       r"conector se ubican sobre la línea planar y se normalizan a su propia "
                       r"impedancia, por lo que muestran el filtro detrás de una alimentación "
                       r"idealmente adaptada). Las dos últimas filas son la placa fabricada (calibración del instrumento). $S_{21}$ es el "
                       r"pico y $S_{11}$ el peor valor dentro de la banda especificada."),
           "label": "tab:launch"},
}


def launch_table_latex(cm: dict, lang: str = "en", summary: str = LAUNCH_SUMMARY) -> str:
    L = LAUNCH_LABELS[lang]
    s = json.load(open(summary))
    rows = []
    for key in ("ms", "cpwg", "cpwg_sma"):
        m = s[key]
        s11 = m["s11w_db"]
        if key == "cpwg_sma" and "palace" in cm:      # same figure as the comparison table
            s11 = cm["palace"]["s11_inband_worst_db"]
        rows.append((L["rows"][key], m["fc_ghz"], m["bw_mhz"], m["il_db"], s11))
    for key, rk in (("SC", "meas"), ("UC", "meas_u")):
        m = cm.get(key)
        if m:
            rows.append((L["rows"][rk], m["fc_ghz"], m["bw_mhz"], m["s21_peak_db"],
                         m["s11_inband_worst_db"]))
    lines = [r"\begin{table}[t]", r"\centering", r"\scriptsize", r"\setlength{\tabcolsep}{2.5pt}",
             r"\caption{" + L["caption"] + "}", r"\label{" + L["label"] + "}",
             r"\begin{tabular}{lcccc}", r"\hline",
             " & ".join(h if "$" in h else f"\\textbf{{{h}}}" for h in L["head"]) + r" \\", r"\hline"]
    for lab, fc, bw, s21, s11 in rows:
        lines.append(f"{lab} & {fc:.3f} & {bw:.0f} & {_tex_minus(f'{s21:.2f}')} & "
                     f"{_tex_minus(f'{s11:.1f}')} \\\\")
    lines += [r"\hline", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def update_marked_block(path: str, name: str, content: str) -> bool:
    """Replace the text between ``<!-- BEGIN siw-table:NAME -->`` / ``<!-- END ... -->``
    in a Markdown file with a raw-LaTeX fenced block. Returns True if the marker exists."""
    begin, end = f"<!-- BEGIN siw-table:{name} -->", f"<!-- END siw-table:{name} -->"
    s = open(path, encoding="utf-8").read()
    i, j = s.find(begin), s.find(end)
    if i < 0 or j < 0:
        return False
    block = f"{begin}\n```{{=latex}}\n{content}\n```\n{end}"
    open(path, "w", encoding="utf-8").write(s[:i] + block + s[j + len(end):])
    return True


# --------------------------------------------------------------------------
# coupling-matrix fit (lossy N=3), same model as docs/final_check/analyze_final.py
# --------------------------------------------------------------------------
def cm_response(f, ms1, m12, d_end, d_mid, iq, spec: FilterSpec | None = None):
    """|S11|, |S21| (dB) of a mirror-symmetric lossy N=3 coupling matrix.
    ``d_*`` are normalised resonator detunings, ``iq`` = 1/Qu."""
    spec = spec or FilterSpec(N=3)
    f0, fbw = spec.f0 / 1e9, spec.FBW
    f = np.asarray(f, float)
    W = np.diag([0, 1, 1, 1, 0.]); R = np.diag([1, 0, 0, 0, 1.])
    M = np.zeros((5, 5))
    for (i, j), v in {(0, 1): ms1, (1, 2): m12, (2, 3): m12, (3, 4): ms1}.items():
        M[i, j] = M[j, i] = v
    M[1, 1] = M[3, 3] = d_end
    M[2, 2] = d_mid
    lam = ((f / f0 - f0 / f) / fbw)[:, None, None]
    A = M[None] + lam * W[None] - 1j * R[None] - 1j * W[None] * iq / fbw
    Ai = np.linalg.inv(A)
    return _db(1 + 2j * Ai[:, 0, 0]), _db(-2j * Ai[:, 4, 0])


def fit_coupling_matrix(c: Curve, spec: FilterSpec | None = None, rng=FIT_RANGE_GHZ) -> dict:
    """Fit a mirror-symmetric lossy N=3 coupling matrix to |S11|, |S21|.

    Returns fitted external/internal coupling errors vs the Chebyshev target,
    end/middle resonator detuning (MHz) and the unloaded Q. Port-side effects
    (connector, launch) are NOT in the model, so on MEASURED data the fit is
    ill-conditioned (Qu trades against the couplings); it is reliable on the
    Palace curve, where it reproduces docs/final_check/analysis.json.
    """
    from scipy.optimize import least_squares
    from .synthesis import chebyshev_g, coupling_matrix
    spec = spec or FilterSpec(N=3)
    f0, fbw = spec.f0 / 1e9, spec.FBW
    M0 = coupling_matrix(chebyshev_g(3, spec.ripple_db), fbw)
    m = (c.f_ghz >= rng[0]) & (c.f_ghz <= rng[1])
    step = max(1, int(m.sum() // 400))             # <=400 points: the fit is smooth
    f, s11, s21 = c.f_ghz[m][::step], c.s11_db[m][::step], c.s21_db[m][::step]
    floor = -35.0   # below this the bench sees leakage the model has no term for

    def resid(y):
        m11, m21 = cm_response(f, *y, spec=spec)
        return np.r_[np.maximum(m11, -30) - np.maximum(s11, -30),
                     0.5 * (np.maximum(m21, floor) - np.maximum(s21, floor))]

    lo = [0.3, 0.3, -2, -2, 0]; hi = [3, 3, 2, 2, .05]
    best = min((least_squares(resid, [M0[0, 1], M0[1, 2], de, dm, 1 / 270], bounds=(lo, hi))
                for de in (-.3, 0, .3) for dm in (-.3, 0, .3)), key=lambda r: r.cost)
    y = best.x
    mhz = lambda d: float(-d * fbw * f0 / 2 * 1000)  # noqa: E731
    return {"source": c.name, "fit_rms_db": float(np.sqrt(np.mean(best.fun ** 2))),
            "params": [float(v) for v in y],
            "M_ext_err_pct": float(100 * (y[0] / M0[0, 1] - 1)),
            "M_int_err_pct": float(100 * (y[1] / M0[1, 2] - 1)),
            "Qe_fitted": float(1 / (fbw * y[0] ** 2)), "Qe_target": float(1 / (fbw * M0[0, 1] ** 2)),
            "k12_fitted": float(fbw * y[1]), "k12_target": float(fbw * M0[1, 2]),
            "end_cavity_detune_mhz": mhz(y[2]), "mid_cavity_detune_mhz": mhz(y[3]),
            "Qu": float(1 / y[4]) if y[4] > 0 else None}


def loss_sweep(fit: dict, qus=(1e6, 270, 229, 180, 150, 130, 100), spec: FilterSpec | None = None) -> list:
    """Forward model: keep the fitted couplings/detunings, vary only the unloaded Q.

    Shows what resonator loss alone does to the response (insertion loss, how
    many reflection zeros survive, depth of the best one). Used to read the
    measured loss as an effective Qu without refitting an ill-conditioned model.
    """
    spec = spec or FilterSpec(N=3)
    f = np.linspace(2.6, 3.2, 1201)
    out = []
    for qu in qus:
        y = list(fit["params"][:4]) + [1.0 / qu]
        s11, s21 = cm_response(f, *y, spec=spec)
        mm = metrics(Curve("cm", f, s11, s21), spec)
        out.append({"Qu": float(qu), "il_db": float(-mm["s21_peak_db"]), "bw_mhz": mm["bw_mhz"],
                    "s11_inband_worst_db": mm["s11_inband_worst_db"],
                    "s11_best_db": mm["s11_best_db"], "n_s11_zeros": mm["n_s11_zeros"]})
    return out


# --------------------------------------------------------------------------
# figures
# --------------------------------------------------------------------------
STYLE = {"palace": ("k", "-", "Palace (fine mesh)"), "cst": ("C2", "-", "CST FD"),
         "SC": ("C3", "-", "VNA, soldered (instrument cal.)"),
         "UC": ("C1", "-", "VNA, unsoldered (instrument cal.)"),
         "SW_S": ("C0", "--", "VNA, soldered (software cal.)"),
         "SW_U": ("C9", "--", "VNA, unsoldered (software cal.)")}


def plot_comparison(curves: dict[str, Curve], spec: FilterSpec, path: str) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    b0, b1 = spec.f1 / 1e9, spec.f2 / 1e9
    fig, ax = plt.subplots(1, 3, figsize=(14, 4.2), gridspec_kw={"width_ratios": [1, 1, 1.15]})
    for key, (col, ls, lab) in STYLE.items():
        if key not in curves:
            continue
        c = curves[key]
        for a, y, win in ((ax[0], c.s21_db, (2.6, 3.2)), (ax[1], c.s11_db, (2.6, 3.2))):
            m = (c.f_ghz >= win[0]) & (c.f_ghz <= win[1])
            a.plot(c.f_ghz[m], y[m], color=col, ls=ls, lw=1.6, label=lab)
    for key, wide, col in (("SC", "SC", "C3"), ("palace_bb", "palace_bb", "k"), ("cst_bb", "cst_bb", "C2")):
        if wide in curves:
            c = curves[wide]
            m = c.f_ghz <= 5.05
            ax[2].plot(c.f_ghz[m], c.s21_db[m], color=col, lw=1.2,
                       label={"SC": "VNA (soldered)", "palace_bb": "Palace", "cst_bb": "CST"}[key])
    for a in ax[:2]:
        a.axvspan(b0, b1, color="#2ca02c", alpha=0.08, label="specified band")
        a.set_xlabel("Frequency (GHz)"); a.grid(alpha=.3)
    ax[0].set(ylabel="|S21| (dB)", ylim=(-40, 1), title="(a) transmission")
    ax[1].set(ylabel="|S11| (dB)", ylim=(-35, 0), title="(b) reflection")
    ax[1].axhline(-16, color="0.5", ls=":", lw=1)
    ax[2].set(xlabel="Frequency (GHz)", ylabel="|S21| (dB)", ylim=(-70, 2), xlim=(0.5, 5.05),
              title="(c) wideband: spurious passbands")
    ax[2].grid(alpha=.3)
    h, l = ax[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, fontsize=8, frameon=False, bbox_to_anchor=(0.36, -0.1))
    ax[2].legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_calibration_check(ds: Dataset, cal: SoftwareCal, path: str) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(14, 3.8))
    raw, sw, ref = ds.dut["SU"], cal.apply(ds.dut["SU"]), ds.dut["SC"]
    f = ref.f / 1e9
    m = (f >= 2.4) & (f <= 3.4)
    for a, (i, j), t in zip(ax, ((1, 0), (0, 0), (1, 1)), ("S21", "S11", "S22")):
        a.plot(f[m], _db(raw.s[m, i, j]), color="0.6", lw=1, label="raw (uncalibrated)")
        a.plot(f[m], _db(ref.s[m, i, j]), "C3", lw=1.6, label="instrument calibration")
        a.plot(f[m], _db(sw.s[m, i, j]), "C0--", lw=1.6, label="software calibration")
        a.set(xlabel="Frequency (GHz)", ylabel=f"|{t}| (dB)", title=f"{t}, soldered board")
        a.grid(alpha=.3)
    ax[0].set_ylim(-45, 2); ax[1].set_ylim(-35, 1); ax[2].set_ylim(-35, 1)
    ax[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return path


Q_SOURCES = ("palace", "cst", "SC", "SW_S")
Q_TEXT = {
    "en": {"src": {"palace": "Palace", "cst": "CST", "SC": "VNA soldered\n(instrument cal.)",
                   "SW_S": "VNA soldered\n(software cal.)"},
           "zoom_src": {"palace": "Palace (fine mesh)", "cst": "CST (FD)", "SC": "VNA, soldered, instrument cal."},
           "th_qlr": "Ripple band\n(1/FBW)", "th_ql": "Theory\n(ideal, -3 dB)", "th_qd": "Theory\n(dielectric,\nPEC walls)", "th_qdc": "Theory\n(dielectric\n+ copper)",
           "ql": r"Loaded $Q_L = f_c/\mathrm{BW}_{-3\,\mathrm{dB}}$", "qu": r"Effective $Q_u$ (from IL)",
           "t_ql": "(a) loaded Q", "t_qu": r"(b) effective unloaded $Q_u$",
           "freq": "Frequency (GHz)", "peak": "peak"},
    "es": {"src": {"palace": "Palace", "cst": "CST", "SC": "VNA soldado\n(cal. instrumento)",
                   "SW_S": "VNA soldado\n(cal. software)"},
           "zoom_src": {"palace": "Palace (malla fina)", "cst": "CST (FD)", "SC": "VNA, soldado, cal. instrumento"},
           "th_qlr": "Banda de\nrizado (1/FBW)", "th_ql": "Teoría\n(ideal, -3 dB)", "th_qd": "Teoría\n(dieléctrico,\nparedes PEC)", "th_qdc": "Teoría\n(dieléctrico\n+ cobre)",
           "ql": r"$Q$ cargado $Q_L = f_c/\mathrm{BW}_{-3\,\mathrm{dB}}$", "qu": r"$Q_u$ efectivo (de la IL)",
           "t_ql": "(a) Q cargado", "t_qu": r"(b) $Q_u$ efectivo",
           "freq": "Frecuencia (GHz)", "peak": "pico"},
}
_Q_COLORS = {"palace": "k", "cst": "C2", "SC": "C3", "SW_S": "C0"}


def plot_q_comparison(cm: dict, spec: FilterSpec, path: str, lang: str = "en") -> str:
    """Bars: loaded Q and effective Qu per source, next to the theoretical values."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    T, th = Q_TEXT[lang], q_theory(spec)
    keys = [k for k in Q_SOURCES if k in cm and cm[k].get("q_loaded")]
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    panels = ((axs[0], "q_loaded", [(T["th_qlr"], th["q_loaded_ripple"]), (T["th_ql"], th["q_loaded"])], T["ql"], T["t_ql"], "{:.1f}"),
              (axs[1], "qu_eff", [(T["th_qd"], th["qu_dielectric"]), (T["th_qdc"], th["qu_dielectric_copper"])],
               T["qu"], T["t_qu"], "{:.0f}"))
    for a, key, theo, ylab, title, fmt in panels:
        labs = [t[0] for t in theo] + [T["src"][k] for k in keys]
        vals = [t[1] for t in theo] + [cm[k][key] for k in keys]
        bars = a.bar(range(len(vals)), vals, color=["0.55"] * len(theo) + [_Q_COLORS[k] for k in keys])
        for b in bars[:len(theo)]:
            b.set_hatch("//"); b.set_edgecolor("w")
        for i, v in enumerate(vals):
            a.text(i, v, fmt.format(v), ha="center", va="bottom", fontsize=9)
        a.set_xticks(range(len(vals))); a.set_xticklabels(labs, fontsize=7)
        a.set(ylabel=ylab, title=title); a.grid(axis="y", alpha=.3)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_q_zoom(curves: dict[str, Curve], cm: dict, path: str, lang: str = "en") -> str:
    """Zoomed |S21| per source with the -3 dB bandwidth drawn as a dotted line."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    T = Q_TEXT[lang]
    keys = [k for k in ("palace", "cst", "SC") if k in curves and k in cm]
    fig, ax = plt.subplots(1, len(keys), figsize=(4.7 * len(keys), 4.2), sharey=True, squeeze=False)
    for a, k in zip(ax[0], keys):
        c, m = curves[k], cm[k]
        w = (c.f_ghz >= 2.6) & (c.f_ghz <= 3.2)
        lo, hi, pk = m["f_lo_ghz"], m["f_hi_ghz"], m["s21_peak_db"]
        thr, fc = pk - 3.0, 0.5 * (m["f_lo_ghz"] + m["f_hi_ghz"])
        a.plot(c.f_ghz[w], c.s21_db[w], color=_Q_COLORS[k], lw=2)
        a.axhline(pk, color="0.7", ls="--", lw=.8)
        a.hlines(thr, lo, hi, colors="0.2", linestyles=":", lw=1.8)
        a.vlines([lo, hi], thr - 0.6, thr + 0.6, colors="0.2", lw=1.2)
        a.annotate("", xy=(lo, thr - 1.2), xytext=(hi, thr - 1.2),
                   arrowprops={"arrowstyle": "<->", "color": "0.2"})
        a.text(fc, thr - 1.7, rf"BW$_{{-3\,\mathrm{{dB}}}}$ = {m['bw_mhz']:.0f} MHz", ha="center", va="top", fontsize=10)
        a.text(fc, pk + .25, f"{T['peak']} {pk:.2f} dB", ha="center", fontsize=8, color="0.4")
        a.text(0.03, 0.04, f"$f_c$ = {m['fc_ghz']:.3f} GHz\n$Q_L = f_c/\\mathrm{{BW}}$ = {m['q_loaded']:.1f}",
               transform=a.transAxes, fontsize=10, va="bottom", bbox={"boxstyle": "round", "fc": "w", "ec": "0.8"})
        a.set(title=T["zoom_src"][k], xlim=(2.70, 3.10), ylim=(-9, 1), xlabel=T["freq"])
        a.grid(alpha=.3)
    ax[0][0].set_ylabel("|S21| (dB)")
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
PAPER_DIR = data_path("docs", "paper")
PAPER_FILES = {"en": "ai_driven_rf_design.md", "es": "Informe_Filtro_SIW_287GHz.md"}


def run(dataset: str = DEFAULT_DATASET, kit: str = "nominal", fit: bool = False, paper: bool = False,
        palace: str = DEFAULT_PALACE, cst: str = DEFAULT_CST, out_name: str = "measure",
        quiet: bool = False) -> dict:
    spec = FilterSpec(N=3)
    fit = fit or paper          # the papers quote the fit / loss sweep, so keep them in sync
    ds = load_dataset(dataset)
    if not ds.dut:
        raise FileNotFoundError(f"no DUT .s2p files in {dataset}")
    cal = SoftwareCal(ds, kit)
    curves = build_curves(ds, cal, palace=palace, cst=cst)
    cm = comparison_metrics(curves, spec)
    res = {"dataset": os.path.relpath(ds.root, data_path()), "software_cal_model": kit,
           "calibration_check": calibration_report(ds, cal, spec), "metrics": cm}
    other = "ideal" if kit == "nominal" else "nominal"
    try:   # how much does the choice of standard model matter? (magnitudes only: the
        # model mainly moves the reference plane, i.e. the phase)
        alt = SoftwareCal(ds, other)
        f = ds.dut["SU"].f / 1e9
        mm = (f >= 2.6) & (f <= 3.2)
        a, b = cal.apply(ds.dut["SU"]), alt.apply(ds.dut["SU"])
        res["standard_model_sensitivity"] = {
            "compared": f"{kit} vs {other}",
            "max_abs_dS21_db": float(np.abs(_db(a.s[mm, 1, 0]) - _db(b.s[mm, 1, 0])).max()),
            "max_abs_dS11_db": float(np.abs(_db(a.s[mm, 0, 0]) - _db(b.s[mm, 0, 0])).max()),
            "mean_dGamma_S11": float(np.abs(a.s[mm, 0, 0] - b.s[mm, 0, 0]).mean())}
    except Exception as e:   # noqa: BLE001 - sensitivity is informational
        res["standard_model_sensitivity"] = {"error": str(e)}
    if fit:
        res["coupling_fit"] = {k: fit_coupling_matrix(curves[k], spec)
                               for k in ("palace", "SC", "UC") if k in curves}
        if "palace" in res["coupling_fit"]:
            res["loss_sweep_palace_couplings"] = loss_sweep(res["coupling_fit"]["palace"], spec=spec)
    # artifacts
    for k in ("SW_S", "SW_U"):
        if k in curves and curves[k].net is not None:
            curves[k].net.write_touchstone(out_s2p(f"{out_name}_{'soldered' if k == 'SW_S' else 'unsoldered'}_swcal"))
    json.dump(res, open(out_data(f"{out_name}_metrics.json"), "w"), indent=2)
    figs = [plot_comparison(curves, spec, out_img(f"{out_name}_comparison.png")),
            plot_calibration_check(ds, cal, out_img(f"{out_name}_calibration_check.png"))]
    for lang, sfx in (("en", ""), ("es", "_es")):
        figs += [plot_q_comparison(cm, spec, out_img(f"{out_name}_q_comparison{sfx}.png"), lang),
                 plot_q_zoom(curves, cm, out_img(f"{out_name}_q_zoom{sfx}.png"), lang)]
    res["q_theory"] = q_theory(spec)
    res["figures"] = figs
    if paper:
        _write_paper_artifacts(ds, cal, curves, cm, res, spec, out_name)
    if not quiet:
        print(comparison_table_md(cm, spec))
        cc = res["calibration_check"]
        for k, v in cc["pairs"].items():
            print(f"software vs instrument cal ({k}): mean dS21 {v['s21_mean_diff_db']:+.2f} dB, "
                  f"mean |dGamma| S11 {v['s11_mean_dgamma']:.3f} S22 {v['s22_mean_dgamma']:.3f}")
        if "thru_check" in cc:
            t = cc["thru_check"]
            print(f"thru check: instrument S21 {t['instrument_s21_db_mean']:+.2f} dB, "
                  f"software {t['software_s21_db_mean']:+.2f} dB (ideal 0)")
        for k, v in res.get("coupling_fit", {}).items():
            print(f"CM fit {k}: Qu={v['Qu']:.0f} k12 {v['k12_fitted']:.4f} (target {v['k12_target']:.4f}) "
                  f"Qe {v['Qe_fitted']:.1f} (target {v['Qe_target']:.1f}) "
                  f"end {v['end_cavity_detune_mhz']:+.0f} MHz mid {v['mid_cavity_detune_mhz']:+.0f} MHz "
                  f"rms {v['fit_rms_db']:.2f} dB")
        for r in res.get("loss_sweep_palace_couplings", []):
            print(f"  forward model, Palace couplings, Qu={r['Qu']:>9.0f}: IL {r['il_db']:.2f} dB, "
                  f"{r['n_s11_zeros']} zeros, best S11 {r['s11_best_db']:.1f} dB")
        print("wrote", *figs, sep="\n  ")
    return res


def _write_paper_artifacts(ds, cal, curves, cm, res, spec, out_name) -> None:
    import shutil
    figs = os.path.join(PAPER_DIR, "figures")
    os.makedirs(figs, exist_ok=True)
    data = os.path.join(PAPER_DIR, "data")
    os.makedirs(data, exist_ok=True)
    shutil.copy2(out_img(f"{out_name}_comparison.png"), os.path.join(figs, "fig_measured_vs_sim.png"))
    shutil.copy2(out_img(f"{out_name}_calibration_check.png"), os.path.join(figs, "fig_calibration_check.png"))
    for sfx in ("", "_es"):
        for kind in ("q_comparison", "q_zoom"):
            shutil.copy2(out_img(f"{out_name}_{kind}{sfx}.png"), os.path.join(figs, f"fig_{kind}{sfx}.png"))
    json.dump({k: v for k, v in res.items() if k != "figures"},
              open(os.path.join(data, "measurement_metrics.json"), "w"), indent=2)
    proc = os.path.join(ds.root, "processed")
    os.makedirs(proc, exist_ok=True)
    for k, name in (("SW_S", "dut_soldered_software_calibrated.s2p"),
                    ("SW_U", "dut_unsoldered_software_calibrated.s2p")):
        if k in curves and curves[k].net is not None:
            curves[k].net.write_touchstone(os.path.join(proc, name[:-4]))
    for lang, fn in PAPER_FILES.items():
        p = os.path.join(PAPER_DIR, fn)
        if os.path.exists(p):
            ok1 = update_marked_block(p, "comparison", comparison_table_latex(cm, spec, lang))
            ok2 = update_marked_block(p, "launch", launch_table_latex(cm, lang))
            print(f"{fn}: comparison table {'updated' if ok1 else 'no marker'}, "
                  f"launch table {'updated' if ok2 else 'no marker'}")


def main(argv: list[str] | None = None) -> int:
    """Pipeline-stage entry (``siw --only measure``): defaults, no argv parsing --
    ``runpy`` hands this module the orchestrator's own sys.argv."""
    run()
    return 0


if __name__ == "__main__":
    main()   # no SystemExit: the pipeline runs this via runpy and must continue to the next stage
