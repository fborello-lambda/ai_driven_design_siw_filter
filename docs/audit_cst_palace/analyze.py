"""Reproduce the CST/Palace audit without running either EM solver.

Run from the repository root: .venv/bin/python docs/audit_cst_palace/analyze.py
The original chat S-values are retained verbatim. Their frequency column is
reconstructed as the float32 2.0 + 0.0016*i grid used by that CST text export.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import skrf
from scipy.signal import find_peaks

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "output/audit_cst_palace"
CST = ROOT / "output/data/cst_runs/cst_freq_solver_cascade_N3_2026-09-06.s2p"
PARAMETERS = ("L_cav1=34.239; L_cav2=35.503; L_cav3=34.239; L_feed=15.4623; "
              "L_taper=15.738; Lsub=166.3816; W_ms=1.6636; Wsub=45.79; "
              "a_siw=39.79; eps_r=3.66; h_air=4.56; h_sub=0.76; p_via=3; "
              "rvia=0.75; t_cu=0.0175; tan_d=0.0037; w_ext=13.96; "
              "w_iris12=14.416; w_iris23=14.416")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    f_chat = np.asarray(2.0 + np.arange(1001) * .0016, dtype=np.float32).astype(float)
    chat = []
    blocks = []
    for name, label in (("s11", "S1,1"), ("s21", "S2,1")):
        values = (HERE / f"cst_chat_{name}_values.txt").read_text().split()
        assert len(values) == 1001, (name, len(values))
        chat.append(np.asarray(values, dtype=float))
        blocks.append(f'#Parameters = {{{PARAMETERS}}}\n'
                      f'#"Frequency / GHz"\t"{label} [Magnitude]"\n'
                      '#------------------------------------\n' +
                      ''.join(f'{f:.13f}\t{v}\n' for f, v in zip(f_chat, values)))
    (HERE / "cst_chat_export.txt").write_text(''.join(blocks))
    # Independent landmarks from the pasted tables catch row shifts.
    assert chat[0][660] == -.37227227852762
    assert chat[1][661] == -28.076268298497
    assert chat[1][544] == -34.839069974162
    assert f'{f_chat[661]:.13f}' == '3.0576000213623'

    network = skrf.Network(CST)
    f = network.f / 1e9
    s = network.s
    assert len(f) == 1001 and np.all(np.diff(f) > 0)
    assert np.all(np.isfinite(s)) and np.all(network.z0 == 50)
    # Cross-check the parser against the nine literal MA columns.
    raw = np.loadtxt(CST, comments=('!', '#'))
    for i, j, k in ((0, 0, 1), (1, 0, 3), (0, 1, 5), (1, 1, 7)):
        np.testing.assert_allclose(s[:, i, j], raw[:, k] * np.exp(1j*np.deg2rad(raw[:, k+1])),
                                   rtol=1e-12, atol=1e-14)
    db = 20*np.log10(np.maximum(abs(s), 1e-300))
    target = int(np.argmin(abs(f - 2.87)))
    metrics = {"source": str(CST.relative_to(ROOT)),
               "sha256": hashlib.sha256(CST.read_bytes()).hexdigest(),
               "format": "GHz S MA R 50; order S11,S21,S12,S22",
               "samples": len(f), "target_sample_ghz": float(f[target]),
               "parameters": re.search(r'! Parameters = (.*)', CST.read_text())[1].strip(),
               "s_parameters": {}}
    for i, j in ((0, 0), (1, 0), (0, 1), (1, 1)):
        y = db[:, i, j]
        lo, hi = int(np.argmin(y)), int(np.argmax(y))
        peaks, _ = find_peaks(y, prominence=3)
        metrics['s_parameters'][f'S{i+1}{j+1}'] = {
            "min_db": float(y[lo]), "min_at_ghz": float(f[lo]),
            "max_db": float(y[hi]), "max_at_ghz": float(f[hi]),
            "target_db": float(y[target]),
            "local_maxima_prominence_3db": [[float(f[k]), float(y[k])] for k in peaks]}
    singular = np.linalg.svd(s, compute_uv=False)[:, 0]
    metrics.update({
        "max_singular_value": float(singular.max()),
        "reciprocity_max_absolute_complex_error": float(abs(s[:, 0, 1]-s[:, 1, 0]).max()),
        "reciprocity_target_magnitude_difference_db": float(db[target, 0, 1]-db[target, 1, 0]),
        "reciprocity_target_phase_difference_deg": float(np.angle(s[target, 0, 1]/s[target, 1, 0], deg=True)),
        "S22_phase_range_deg": [float(np.angle(s[:, 1, 1], deg=True).min()),
                                 float(np.angle(s[:, 1, 1], deg=True).max())],
        "target_power_fractions_as_exported": {
            "reflected": float(abs(s[target, 0, 0])**2),
            "transmitted": float(abs(s[target, 1, 0])**2)},
        "chat_previous_td": {"S11_min_db": float(chat[0].min()),
                             "S21_max_db": float(chat[1].max()),
                             "S21_max_at_ghz": float(f_chat[np.argmax(chat[1])])}})

    # Hypothesis diagnostic only: this input impedance is derived with port 1
    # matched. It is NOT a measurement of the CST port's modal impedance.
    z_from_s22 = 50*(1+s[:, 1, 1])/(1-s[:, 1, 1])
    eta_ptfe = 376.730313668 / np.sqrt(2.08)
    hypothetical_fc = f*np.sqrt(1+(eta_ptfe/z_from_s22.real)**2)
    metrics['port2_hypothesis'] = {
        "interpretation": "Inferred matched-input impedance resembles magnitude of a below-cutoff TE impedance; requires CST mode report to confirm.",
        "zin2_at_target_ohm": float(z_from_s22[target].real),
        "hypothetical_TE_cutoff_ghz_range": [float(hypothetical_fc.min()), float(hypothetical_fc.max())]}

    for name, arr in [('cst_frequency_magnitude.csv',
                       np.column_stack([f, db[:, 0, 0], db[:, 1, 0], db[:, 0, 1], db[:, 1, 1]])),
                      ('cst_previous_td_magnitude.csv', np.column_stack([f_chat, *chat]))]:
        np.savetxt(HERE / name, arr, delimiter=',', fmt='%.13g',
                   header='f_GHz,S11_dB,S21_dB' + (',S12_dB,S22_dB' if arr.shape[1] == 5 else ''), comments='')

    historical = json.loads(next((ROOT/'golden/cascade_N3').glob('*taoglas.s11s21.json')).read_text())
    refined = json.loads((OUT/'refined_sweep.json').read_text())
    old_fine = json.loads((ROOT/'output/data/mesh_convergence_cascade_N3.json').read_text())
    experiments = json.loads((OUT/'diagnostic_solves.json').read_text())
    metrics['palace_refined'] = {k: refined[k] for k in ('il','s11w','bw','fc_3db','fc','f_lo','f_hi')}
    metrics['palace_short_diagnostics'] = {}
    for label, values in experiments.items():
        audit = json.loads((OUT/f'{label}_mesh.json').read_text())
        log = (ROOT/f'output/data/audit_{label}.log').read_text()
        zp = re.findall(r'Port (\d+), mode 1:.*Z_PV = ([\d.e+-]+)', log)
        metrics['palace_short_diagnostics'][label] = {
            'f_ghz': values['f'], 's11_db': values['s11_db'], 's21_db': values['s21_db'],
            'port_Z_PV_ohm_first_frequency': dict(zp[:2]),
            **{key: audit[key] for key in ('tetrahedra','ports','quality','unclassified_exterior','settings')}}
    for name, values, freq_key in [('palace_historical_magnitude.csv', historical, 'f_ghz'),
                                   ('palace_refined_ports_magnitude.csv', refined, 'f'),
                                   ('palace_previous_fine_magnitude.csv', old_fine, 'f_ghz')]:
        np.savetxt(HERE/name, np.column_stack([values[freq_key], values['s11_db'], values['s21_db']]),
                   delimiter=',', fmt='%.13g', header='f_GHz,S11_dB,S21_dB', comments='')
    # Keep real phases without inventing the unexcited S12 and S22 columns.
    shutil.copy2(ROOT/'output/data/postpro/audit_refined_sweep/port-S.csv',
                 HERE/'palace_refined_S11_S21_with_phase.csv')

    fig, axs = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    for ax, key, ij, label in [(axs[0,0], 's11_db', (0,0), 'S11'),
                               (axs[0,1], 's21_db', (1,0), 'S21')]:
        ax.plot(f, db[:,ij[0],ij[1]], label='CST frecuencia (nuevo)', color='tab:red')
        ax.plot(f_chat, chat[0 if label=='S11' else 1], label='CST tiempo (mensaje)', color='0.55', alpha=.7)
        ax.plot(historical['f_ghz'], historical[key], label='Palace histórico', color='tab:blue', ls='--')
        ax.plot(refined['f'], refined[key], label='Palace puertos refinados', color='tab:green')
        ax.set(title=f'{label}: comparación', xlabel='Frecuencia (GHz)', ylabel='Magnitud (dB)',
               xlim=(2.6,3.2), ylim=((-45,1) if label=='S11' else (-135,3)))
        ax.axvspan(2.79825,2.94175,color='green',alpha=.06)
        ax.grid(alpha=.25); ax.legend(fontsize=8)
    ax=axs[1,0]
    for i,j in ((0,0),(1,0),(0,1),(1,1)):
        ax.plot(f,db[:,i,j],label=f'S{i+1}{j+1}')
    ax.set(title='CST frecuencia: cuatro parámetros',xlabel='Frecuencia (GHz)',ylabel='Magnitud (dB)')
    ax.legend();ax.grid(alpha=.25)
    ax=axs[1,1]
    for label, values in experiments.items():
        ax.plot(values['f'],values['s11_db'],'o--',label=label)
    ax.set(title='Palace: sensibilidad (solo 3 frecuencias)',xlabel='Frecuencia (GHz)',ylabel='S11 (dB)')
    ax.legend(fontsize=8);ax.grid(alpha=.25)
    fig.suptitle('Auditoría CST / Palace — N=3, mismas dimensiones nominales',fontsize=15)
    fig.savefig(HERE/'comparison_cst_palace.png',dpi=170)
    plt.close(fig)
    (HERE/'audit_metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
    print(json.dumps({k:v for k,v in metrics.items() if k!='palace_short_diagnostics'},indent=2))


if __name__=='__main__':
    main()
