"""3D renders of the three launch variants (see run_launch.py): whole board +
a close-up of the input launch. Each render runs in its own subprocess under
xvfb-run (gmsh's offscreen renderer can't be reused in-process).

Run from the repo root: uv run python docs/launch_comparison/render.py
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_launch import GOLDEN, VARIANTS  # noqa: E402

OUT = Path('output/launch_comparison')  # intermediates; compare.py builds renders.png
VIEWS = {
    'board': dict(GraphicsWidth=1400, GraphicsHeight=700, hide_air=1),
    # high-res, board axis horizontal: the launch close-up is cropped from it
    'hires': dict(GraphicsWidth=5400, GraphicsHeight=2400, RotationX=45,
                  RotationZ=0, hide_air=1),
}

def render(variant: str, view: str, extra: dict) -> Path:
    params = json.loads(Path(GOLDEN).read_text())['params']
    params.update({k: v for k, v in VARIANTS[variant].items() if k not in ('port_mesh_size', 'port_mode')})
    params['render_view'] = {k: v for k, v in extra.items() if v is not None}
    path = OUT / f'render_{variant}_{view}.png'
    payload = {'topology': 'cascade', 'spec': {'N': 3}, 'params': params,
               'out_name': f'render_{variant}_tmp.msh', 'render_path': str(path.resolve())}
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as fh:
        json.dump(payload, fh)
    cmd = [sys.executable, '-m', 'siwfilter.cli', '_render-worker', fh.name]
    if not os.environ.get('DISPLAY') and shutil.which('xvfb-run'):
        cmd = ['xvfb-run', '-a', '-s', '-screen 0 5600x2600x24'] + cmd
    cp = subprocess.run(cmd, capture_output=True, text=True)
    os.remove(fh.name)
    if cp.returncode:
        raise SystemExit(cp.stderr[-2000:])
    print('wrote', path)
    return path

if __name__ == '__main__':
    views = sys.argv[1:] or list(VIEWS)
    for v in VARIANTS:
        for view in views:
            render(v, view, VIEWS[view])
