"""Build a standalone CST diagnostic ZIP without changing the production exporter."""
from pathlib import Path
import ast
import hashlib
import json
import operator
import re
import shutil
import subprocess
import zipfile

import numpy as np
from siwfilter.config import FilterSpec
from siwfilter.cst_export import generate_bas, _hist
from siwfilter.topologies.cascade import CascadeTopology
from siwfilter.topologies.launch import TAOGLAS_CPWG

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PACKAGE = ROOT/'output/cst_auditoria_2026-09-06'


def control_macro():
    """Straight coax using only geometric/port commands already used by the exporter."""
    ri, ro = TAOGLAS_CPWG['sma_rin_mm'], TAOGLAS_CPWG['sma_rout_mm']
    rs = ro+.3
    s = ["' Standalone coax control, 12 mm, nominal 50 ohm.\n"
         "' Select Frequency Domain Solver in the GUI AFTER running this macro.\n"
         "' No local CST execution validation.\nOption Explicit\nSub Main\nResetAll\n"]
    s.append(_hist('units', ['With Units','.Geometry "mm"','.Frequency "GHz"','.Time "ns"','End With']))
    s.append(_hist('frequency', ['Solver.FrequencyRange "2.0", "3.6"']))
    s.append(_hist('PTFE', ['With Material','.Reset','.Name "PTFE_sma"','.Folder ""',
                           '.Type "Normal"','.Epsilon "2.08"','.Mu "1"',
                           '.TanD "0.0004"','.TanDFreq "2.87"','.TanDGiven "True"',
                           '.TanDModel "ConstTanD"','.Create','End With']))
    for name, material, inner, outer in [('pin','PEC',0.,ri),('ptfe','PTFE_sma',ri,ro),
                                         ('shield','PEC',ro,rs)]:
        s.append(_hist(name, ['With Cylinder','.Reset',f'.Name "{name}"',
                             '.Component "component1"',f'.Material "{material}"','.Axis "x"',
                             f'.Outerradius "{outer:.4f}"',f'.Innerradius "{inner:.4f}"',
                             '.Xrange "0", "12"','.Ycenter "0"','.Zcenter "0"',
                             '.Segments "0"','.Create','End With']))
    s.append(_hist('background', ['With Background','.ResetBackground','.Type "Normal"',
                                 '.XminSpace "0"','.XmaxSpace "0"',
                                 '.YminSpace "2"','.YmaxSpace "2"',
                                 '.ZminSpace "2"','.ZmaxSpace "2"','End With']))
    s.append(_hist('boundaries', ['With Boundary']+
                   [f'.{axis}{end} "open"' for axis in 'XYZ' for end in ('min','max')]+
                   ['.ApplyInAllDirections "False"','End With']))
    for n,x,orient in [(1,0,'xmin'),(2,12,'xmax')]:
        s.append(_hist(f'coax port {n}', ['With Port','.Reset',f'.PortNumber "{n}"',
                     '.NumberOfModes "1"','.Coordinates "Free"',f'.Orientation "{orient}"',
                     '.PortOnBound "True"',f'.Xrange "{x}", "{x}"',
                     f'.Yrange "{-rs:.4f}", "{rs:.4f}"',
                     f'.Zrange "{-rs:.4f}", "{rs:.4f}"','.Create','End With']))
    s.append('MsgBox "Coax control built. Select Frequency Domain Solver and inspect both TEM port modes."\nEnd Sub\n')
    return ''.join(s)


def read_blocks(macro):
    """Decode emitted VBA history text for independent numerical geometry checks."""
    blocks=[]
    pattern = r'^AddToHistory "([^"\n]+)", (.*?)(?=^AddToHistory |^MsgBox|^End Sub|\Z)'
    for match in re.finditer(pattern, macro, re.M|re.S):
        lines = [v.replace('""','"') for v in re.findall(r'"((?:[^"\n]|"")*)"',match[2])]
        if not lines:
            continue
        fields={}; points=[]
        for line in lines:
            field=re.match(r'\.(\w+)\s+(.*)',line)
            if field:
                values=re.findall(r'"([^"]*)"',field[2])
                fields[field[1]]=values
                if field[1] in ('Point','LineTo'):
                    points.append(values)
        blocks.append({'kind':lines[0], 'fields':fields, 'points':points})
    return blocks


def number(expr, parameters):
    operations={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv}
    def visit(node):
        if isinstance(node,ast.Constant) and isinstance(node.value,(int,float)):
            return node.value
        if isinstance(node,ast.Name):
            return parameters[node.id]
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
            return (-1 if isinstance(node.op,ast.USub) else 1)*visit(node.operand)
        if isinstance(node,ast.BinOp) and type(node.op) in operations:
            return operations[type(node.op)](visit(node.left),visit(node.right))
        raise ValueError(f'Unsupported numeric expression: {expr}')
    return float(visit(ast.parse(expr,mode='eval').body))


def check_filter(macro):
    parameters={k:float(v) for k,v in re.findall(r'^StoreParameter "([^"]+)", "([^"]+)"',macro,re.M)}
    blocks=read_blocks(macro)
    objects={b['fields']['Name'][0]:b for b in blocks if b['kind'] in ('With Cylinder','With Brick','With Extrude')}
    ports={b['fields']['PortNumber'][0]:b for b in blocks if b['kind']=='With Port'}
    assert set(ports)=={'1','2'}
    assert 'TD-S' not in macro and 'With Mesh' not in macro and 'With Solver' not in macro
    assert not any('_clip' in n or 'ground_shoe' in n for n in objects)
    assert sum(n.startswith('via') for n in objects)==102
    assert sum(n.startswith('gndvia') for n in objects)==16
    for b in objects.values():
        for axis in 'XYZ':
            if axis+'range' in b['fields']:
                a,z=[number(x,parameters) for x in b['fields'][axis+'range']]
                assert z>a, (b['fields']['Name'],axis,a,z)
    for end,n,index in [('in','1',0),('out','2',1)]:
        for part in ('pin','ptfe','shield'):
            fields=objects[f'sma_{end}_{part}']['fields']
            assert number(fields['Zcenter'][0],parameters)==parameters['h_sub']
            xr=[number(x,parameters) for x in fields['Xrange']]
            assert abs(xr[1]-xr[0]-6)<1e-10
            port_x=number(ports[n]['fields']['Xrange'][0],parameters)
            assert abs(xr[index]-port_x)<1e-10
        pin=objects[f'sma_{end}_pin']['fields']
        ptfe=objects[f'sma_{end}_ptfe']['fields']
        shield=objects[f'sma_{end}_shield']['fields']
        assert number(pin['Outerradius'][0],parameters)==number(ptfe['Innerradius'][0],parameters)
        assert number(ptfe['Outerradius'][0],parameters)==number(shield['Innerradius'][0],parameters)

    # Compare actual emitted feed + flare areas against the actual Palace
    # ten-vertex trace from the retained CAD/mesh result, not just labels.
    def area(points):
        a=np.asarray(points);return abs(np.sum(a[:,0]*np.roll(a[:,1],-1)-a[:,1]*np.roll(a[:,0],-1)))/2
    emitted={name:[[number(x,parameters) for x in xy] for xy in objects[name]['points']]
             for name in ('feed_in','taper_in','feed_out','taper_out')}
    palace=json.loads((ROOT/'output/audit_cst_palace/original_mesh_result.json').read_text())
    # That pre-fix metadata used an envelope; use the corrected actual mesh
    # result geometry from the independent ten-vertex trace helper instead.
    from siwfilter.palace_dualmode_driven import feed_trace_poly
    launch=palace['launch_geom']
    x0=number('-(L_taper+L_feed)',parameters)
    actual=feed_trace_poly(x0,-parameters['L_taper'],0,parameters['W_ms'],
                          -parameters['a_siw']/2,parameters['a_siw']/2,
                          launch['w_pad'],x0+9,x0+5)
    area_in=area(emitted['feed_in'])+area(emitted['taper_in'])
    assert abs(area_in-area(actual))<.005
    assert abs(area_in-area(emitted['feed_out'])-area(emitted['taper_out']))<.005
    return {'checks':'passed numerical dimensions, port planes, radii, counts and trace areas',
            'filter_vias':102,'ground_stitch_vias':16,'emitted_solids':len(objects),
            'cst_execution_validated':False,'input_trace_area_mm2':area_in}


def main():
    PACKAGE.mkdir(parents=True,exist_ok=True)
    golden_path=next((ROOT/'golden/cascade_N3').glob('*taoglas.json'))
    golden=json.loads(golden_path.read_text())
    g=CascadeTopology()._geometry(FilterSpec(N=3),golden['params'])
    macro=generate_bas(g,launch=TAOGLAS_CPWG,flat_sma_ground=False)
    start=macro.index("' ---- mesh + solver setup")
    finish=macro.index('MsgBox',start)
    macro=macro[:start]+"' Select Frequency Domain Solver, all ports, in the GUI.\n"+macro[finish:]
    macro=macro.replace('then run the Time Domain solver.', 'select Frequency Domain Solver and verify both port modes.')
    macro="' DIAGNOSTIC PACKAGE: geometry only, frequency solver configured in GUI.\n"+macro
    checks=check_filter(macro)
    control=control_macro()
    assert sum(b['kind']=='With Cylinder' for b in read_blocks(control))==3
    assert sum(b['kind']=='With Port' for b in read_blocks(control))==2
    assert 'With Solver' not in control and 'TD-S' not in control
    for name,text in [('00_coaxial_control.bas',control),('01_filtro_geometria.bas',macro)]:
        (PACKAGE/name).write_bytes(text.replace('\n','\r\n').encode('utf-8'))
    files=['LEEME_PRIMERO.md','AUDITORIA.md','audit_metrics.json','comparison_cst_palace.png',
           'cst_chat_export.txt','cst_frequency_magnitude.csv','cst_previous_td_magnitude.csv',
           'palace_historical_magnitude.csv','palace_refined_ports_magnitude.csv',
           'palace_previous_fine_magnitude.csv','palace_refined_S11_S21_with_phase.csv']
    for name in files:
        shutil.copy2(HERE/name,PACKAGE/name)
    shutil.copy2(ROOT/'output/data/cst_runs/cst_freq_solver_cascade_N3_2026-09-06.s2p',
                 PACKAGE/'cst_recibido_frequency.s2p')
    shutil.copy2(golden_path,PACKAGE/'palace_historical_provenance.json')
    for name in ['AUDITORIA','LEEME_PRIMERO']:
        subprocess.run(['pandoc',str(PACKAGE/f'{name}.md'),'-s','--embed-resources',
                        '--metadata',f'title={name}', '-o',str(PACKAGE/f'{name}.html')],
                       cwd=PACKAGE,check=True)
        shutil.copy2(PACKAGE/f'{name}.html',HERE/f'{name}.html')
    manifest={'git_base':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'exporter_sha256':hashlib.sha256((ROOT/'src/siwfilter/cst_export.py').read_bytes()).hexdigest(),
              'validation':checks,'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                         for p in sorted(PACKAGE.iterdir()) if p.is_file() and p.name!='MANIFEST.json'}}
    (PACKAGE/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    archive=PACKAGE.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for path in sorted(PACKAGE.iterdir()):
            if path.is_file():z.write(path,arcname=f'{PACKAGE.name}/{path.name}')
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name,digest in manifest['files'].items():
            assert hashlib.sha256(z.read(f'{PACKAGE.name}/{name}')).hexdigest()==digest
    print(json.dumps({'zip':str(archive),'bytes':archive.stat().st_size,'validation':checks},indent=2))


if __name__=='__main__':
    main()
