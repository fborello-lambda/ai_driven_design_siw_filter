"""Chebyshev filter synthesis for the inline coupled-cavity SIW bandpass.

Implements the lowpass g-value recursion (Hong & Lancaster, "Microstrip Filters
for RF/Microwave Applications", Ch. 3), maps it to inter-resonator coupling
coefficients k[i,i+1] and external quality factor Qe (sec. 7 of CLAUDE.md),
builds the (N+2) coupling matrix (Cameron, TMTT 2003), and generates the
target S-parameters which are written to ``target.s2p`` for later comparison.

Run:  uv run python synthesis.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .config import SPEC, FilterSpec, out_s2p, out_img


# ---------------------------------------------------------------------------
# 1. Chebyshev lowpass prototype g-values  (Hong & Lancaster, eqs. 3.10-3.12)
# ---------------------------------------------------------------------------
def chebyshev_g(N: int, ripple_db: float) -> np.ndarray:
    """Return g0..g_{N+1} for an equal-ripple (Chebyshev) lowpass prototype.

    Verified against the canonical N=3, 0.1 dB table:
        g1=1.0316, g2=1.1474, g3=1.0316, g4=1.0
    """
    beta = math.log(1.0 / math.tanh(ripple_db / 17.37))   # = ln(coth(LAr/17.37))
    gamma = math.sinh(beta / (2.0 * N))

    a = [0.0] + [math.sin((2 * k - 1) * math.pi / (2 * N)) for k in range(1, N + 1)]
    b = [0.0] + [gamma**2 + math.sin(k * math.pi / N) ** 2 for k in range(1, N + 1)]

    g = [0.0] * (N + 2)
    g[0] = 1.0
    g[1] = 2.0 * a[1] / gamma
    for k in range(2, N + 1):
        g[k] = (4.0 * a[k - 1] * a[k]) / (b[k - 1] * g[k - 1])
    # Load termination: 1 for odd N, coth^2(beta/4) for even N.
    g[N + 1] = 1.0 if N % 2 == 1 else (1.0 / math.tanh(beta / 4.0)) ** 2
    return np.array(g)


# ---------------------------------------------------------------------------
# 2. Coupling coefficients and external Q  (CLAUDE.md sec. 7)
# ---------------------------------------------------------------------------
def coupling_coeffs(g: np.ndarray, FBW: float) -> np.ndarray:
    """Inter-resonator coupling k[i,i+1] = FBW / sqrt(g_i*g_{i+1}), i=1..N-1.

    These are *frequency-independent* (depend only on g-values and FBW).
    """
    N = len(g) - 2
    return np.array([FBW / math.sqrt(g[i] * g[i + 1]) for i in range(1, N)])


def external_q(g: np.ndarray, FBW: float) -> tuple[float, float]:
    """Input/output external quality factors (Qe1, QeN).

    Qe = g0*g1 / FBW  on the input side; symmetric structure -> output uses
    g_N*g_{N+1} / FBW.
    """
    N = len(g) - 2
    qe_in = g[0] * g[1] / FBW
    qe_out = g[N] * g[N + 1] / FBW
    return qe_in, qe_out


# ---------------------------------------------------------------------------
# 3. (N+2) coupling matrix  (Cameron, TMTT 2003)
# ---------------------------------------------------------------------------
def coupling_matrix(g: np.ndarray, FBW: float) -> np.ndarray:
    """Build the normalized (N+2)x(N+2) coupling matrix M.

    Index 0 = source S, indices 1..N = resonators, index N+1 = load L.
    Normalized entries:
        M[S,1]   = 1/sqrt(g0*g1)
        M[i,i+1] = 1/sqrt(g_i*g_{i+1})
        M[N,L]   = 1/sqrt(g_N*g_{N+1})
    (Physical k[i,i+1] = FBW * M[i,i+1]; Qe relates via M_S1 = 1/sqrt(qe1).)
    """
    N = len(g) - 2
    size = N + 2
    M = np.zeros((size, size))

    ms1 = 1.0 / math.sqrt(g[0] * g[1])
    M[0, 1] = M[1, 0] = ms1
    for i in range(1, N):
        m = 1.0 / math.sqrt(g[i] * g[i + 1])
        M[i, i + 1] = M[i + 1, i] = m
    mnl = 1.0 / math.sqrt(g[N] * g[N + 1])
    M[N, N + 1] = M[N + 1, N] = mnl
    return M


def sparams_from_matrix(M: np.ndarray, FBW: float, f0: float,
                        freqs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate S11, S21 from the (N+2) coupling matrix over ``freqs`` [Hz].

    Uses A = M + Omega*W - j*R  with the bandpass frequency mapping
        Omega = (1/FBW) * (f/f0 - f0/f).
    S11 = 1 + 2j [A^-1]_{S,S},  S21 = -2j [A^-1]_{L,S}.
    """
    size = M.shape[0]

    W = np.eye(size)
    W[0, 0] = 0.0
    W[size - 1, size - 1] = 0.0

    R = np.zeros((size, size))
    R[0, 0] = 1.0
    R[size - 1, size - 1] = 1.0

    s11 = np.empty(freqs.shape, dtype=complex)
    s21 = np.empty(freqs.shape, dtype=complex)
    for idx, f in enumerate(freqs):
        Omega = (1.0 / FBW) * (f / f0 - f0 / f)
        A = M + Omega * W - 1j * R
        Ainv = np.linalg.inv(A)
        s11[idx] = 1.0 + 2j * Ainv[0, 0]
        s21[idx] = -2j * Ainv[size - 1, 0]
    return s11, s21


# ---------------------------------------------------------------------------
# 4. High-level synthesis result + s2p export
# ---------------------------------------------------------------------------
@dataclass
class SynthesisResult:
    spec: FilterSpec
    g: np.ndarray
    k: np.ndarray
    qe_in: float
    qe_out: float
    M: np.ndarray


def synthesize(spec: FilterSpec = SPEC) -> SynthesisResult:
    g = chebyshev_g(spec.N, spec.ripple_db)
    k = coupling_coeffs(g, spec.FBW)
    qe_in, qe_out = external_q(g, spec.FBW)
    M = coupling_matrix(g, spec.FBW)
    return SynthesisResult(spec=spec, g=g, k=k, qe_in=qe_in, qe_out=qe_out, M=M)


def write_target_s2p(res: SynthesisResult, path: str | None = None,
                     span: float = 0.25, n_points: int = 801):
    """Generate the ideal target response and save it as a Touchstone file.

    ``span`` is the fractional frequency span around f0 (e.g. 0.25 -> +-25%).
    Requires scikit-rf.
    """
    import skrf as rf

    if path is None:
        path = out_s2p("target.s2p")
    spec = res.spec
    f = np.linspace(spec.f0 * (1 - span), spec.f0 * (1 + span), n_points)
    s11, s21 = sparams_from_matrix(res.M, spec.FBW, spec.f0, f)

    s = np.zeros((n_points, 2, 2), dtype=complex)
    s[:, 0, 0] = s11
    s[:, 1, 0] = s21
    s[:, 0, 1] = s21    # reciprocal
    s[:, 1, 1] = s11    # symmetric
    ntwk = rf.Network(frequency=rf.Frequency.from_f(f, unit="Hz"),
                      s=s, z0=50.0, name="siw_target")
    ntwk.write_touchstone(path, write_z0=True)
    return ntwk, f, s11, s21


if __name__ == "__main__":
    res = synthesize(SPEC)
    spec = res.spec

    print(f"=== Chebyshev synthesis: N={spec.N}, ripple={spec.ripple_db} dB, "
          f"FBW={spec.FBW*100:.1f}% @ {spec.f0/1e9:.3f} GHz ===\n")

    print("g-values (g0..g_{N+1}):")
    for i, gi in enumerate(res.g):
        print(f"  g{i} = {gi:.4f}")
    print("  (CLAUDE.md check N=3,0.1dB: g1=1.0316 g2=1.1474 g3=1.0316 g4=1.0)\n")

    print("Inter-resonator coupling coefficients:")
    for i, ki in enumerate(res.k, start=1):
        print(f"  k{i}{i+1} = {ki:.4f}")
    print("  (CLAUDE.md check: k12=k23 ~ 0.046)\n")

    print("External Q:")
    print(f"  Qe_in  = {res.qe_in:.4f}")
    print(f"  Qe_out = {res.qe_out:.4f}")
    print("  (CLAUDE.md check: Qe ~ 20.6)\n")

    print("(N+2) coupling matrix M [S,1..N,L]:")
    with np.printoptions(precision=4, suppress=True):
        print(res.M)

    ntwk, f, s11, s21 = write_target_s2p(res)
    print(f"\nWrote {out_s2p('target.s2p')}")

    # Quick passband sanity check
    fmask = (f >= spec.f1) & (f <= spec.f2)
    # floor magnitudes so reflection zeros (|S|=0) don't blow up log10
    s21_db = 20 * np.log10(np.maximum(np.abs(s21), 1e-12))
    s11_db = 20 * np.log10(np.maximum(np.abs(s11), 1e-12))
    print(f"In-band |S21| min = {s21_db[fmask].min():.3f} dB "
          f"(ideal lossless ~0 dB)")
    print(f"In-band |S11| max = {s11_db[fmask].max():.3f} dB "
          f"(return loss; ripple {spec.ripple_db} dB -> RL ~ "
          f"{-10*math.log10(1-10**(-spec.ripple_db/10)):.1f} dB)")

    # Optional plot
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(f / 1e9, s21_db, label="|S21|")
        ax.plot(f / 1e9, s11_db, label="|S11|")
        ax.axvspan(spec.f1 / 1e9, spec.f2 / 1e9, color="green", alpha=0.1,
                   label="passband")
        ax.set_xlabel("Frequency [GHz]")
        ax.set_ylabel("Magnitude [dB]")
        ax.set_ylim(-60, 2)
        ax.set_title(f"SIW target response — N={spec.N}, {spec.f0/1e9:.3f} GHz")
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_img("target_response.png"), dpi=120)
        print(f"Wrote {out_img('target_response.png')}")
    except Exception as e:
        print(f"(plot skipped: {e})")
