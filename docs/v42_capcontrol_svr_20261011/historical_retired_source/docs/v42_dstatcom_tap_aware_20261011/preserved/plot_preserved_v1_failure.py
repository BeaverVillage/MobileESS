"""Read-only reproducible SVG figures of the preserved failed V1 experiment."""
import csv
import hashlib
import html
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'V1_FAILURE_FIGURES'
ON=ROOT/'B2_MAY01_FROZEN_ON_01'
OFF=ROOT/'B2_MAY01_FROZEN_OFF_01'
SAVED=ROOT/'V1_INDEPENDENT_SAVED_AUDIT'

def record(p):
    return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)

def text(x,y,value,size=14,color='#334155'):
    return f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" fill="{color}">{html.escape(str(value))}</text>'

def line(x1,y1,x2,y2,color='#cbd5e1',width=1):
    return f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{color}" stroke-width="{width}"/>'

def graph(y,height,series,ymin,ymax,title,threshold=None):
    left,right,top,bottom=90,1160,y+32,y+height-35
    body=text(90,y+12,title,18)
    for value in np.linspace(ymin,ymax,5):
        yy=bottom-(value-ymin)/(ymax-ymin)*(bottom-top)
        body+=line(left,yy,right,yy)+text(18,yy+5,f'{value:.3g}')
    for slot in (0,24,48,72,95):
        xx=left+slot/95*(right-left)
        body+=text(xx-8,bottom+22,slot)
    for name,values,color in series:
        points=' '.join(f'{left+i/95*(right-left):.3f},{bottom-(value-ymin)/(ymax-ymin)*(bottom-top):.3f}' for i,value in enumerate(values))
        body+=f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>'
    if threshold is not None:
        yy=bottom-(threshold-ymin)/(ymax-ymin)*(bottom-top)
        body+=line(left,yy,right,yy,'#dc2626',1.5)
    for i,(name,_,color) in enumerate(series):
        body+=text(780+i*150,y+12,name,13,color)
    return body

def save(name,body,height):
    document=f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}"><rect width="1200" height="{height}" fill="white"/><g font-family="Arial, sans-serif">{body}</g></svg>'
    (OUT/name).write_text(document,encoding='utf8')

def main():
    OUT.mkdir(exist_ok=True)
    on_receipt=json.loads((ON/'REPLAY_RESULT.json').read_text(encoding='utf8'))
    off_receipt=json.loads((OFF/'REPLAY_RESULT.json').read_text(encoding='utf8'))
    sources=[ON/'FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz',OFF/'FRESH/fresh/OPENDSS_PHASE_ARRAYS.npz',
        SAVED/'SLOT96_Q_TAPS_LOSS_NETWORK.csv',SAVED/'PHASE108_APPARENT_RESERVE.csv']
    for result,path in ((on_receipt,sources[0]),(off_receipt,sources[1])):
        if record(path)!=result['metrics']['raw_AC_receipt']:
            raise PermissionError('PRESERVED_V1_FIGURE_RAW_SHA_DRIFT')
    with np.load(sources[0],allow_pickle=False) as archive:
        v=archive['voltage_pu'].copy();nodes=archive['node_names'].astype(str).copy()
    with np.load(sources[1],allow_pickle=False) as archive:
        baseline=archive['voltage_pu'].copy()
        if not np.array_equal(nodes,archive['node_names'].astype(str)):
            raise PermissionError('PRESERVED_V1_NODE_AXES_DRIFT')
    with sources[2].open(encoding='utf-8-sig') as stream: slots=list(csv.DictReader(stream))
    with sources[3].open(encoding='utf-8-sig') as stream: phases=list(csv.DictReader(stream))
    numbers=lambda key:np.array([float(row[key]) for row in slots])
    head=text(40,34,'Preserved V1 failure: 36 devices / 27.75 MVAr / no deployment',22)
    head+=text(40,58,'Same frozen B2 May01 plan and Actual input. All 19 original cells fixed; 921 remote upper violations created.',14)
    body=head+graph(82,215,[('OFF',baseline.max(axis=1),'#2563eb'),('V1 ON',v.max(axis=1),'#ea580c')],1.02,1.075,'Maximum original feeder voltage [pu]',1.05)
    body+=graph(312,215,[('Absorbed Q',-numbers('sum_signed_DSTATCOM_Q_kvar')/1000,'#7c3aed')],0,3.6,'Total D-STATCOM absorption [MVAr]')
    body+=graph(542,215,[('OFF',numbers('reg6_OFF_tap'),'#2563eb'),('V1 ON',numbers('reg6_ON_tap'),'#ea580c')],1.0,1.11,'Regulator 6 tap ratio')
    body+=graph(772,215,[('OFF',numbers('off_line_max_percent'),'#2563eb'),('V1 ON',numbers('on_line_max_percent'),'#ea580c')],20,140,'Maximum original feeder line loading [%]',100)
    body+=text(40,1010,'Slot index 0..95. Recorded associations; fixed-tap and staged counterfactual AC are required for causal attribution.',13)
    save('V1_Q_TAP_REMOTE_VOLTAGE_LINE.svg',body,1030)
    bad=np.flatnonzero(((v<.95)|(v>1.05)).any(axis=0))
    body=head+text(40,84,f'All {len(bad)} violating original node-phases; all 921 cells are upper violations. Lower violations: 0.',15)
    for row,index in enumerate(bad):
        yy=110+row*23;body+=text(20,yy+13,nodes[index],12)
        for slot in range(96):
            exceed=max(0.,v[slot,index]-1.05)
            color='#edf2f7' if exceed==0 else '#fb923c' if exceed<.005 else '#ef4444' if exceed<.01 else '#991b1b'
            body+=f'<rect x="{205+slot*9.7:.2f}" y="{yy}" width="9.4" height="19" fill="{color}"/>'
    for slot in (0,24,48,72,95):body+=text(205+slot*9.7,106,slot,12)
    body+=text(40,135+len(bad)*23,'Orange <0.005 pu; red 0.005..0.010 pu; dark red >=0.010 pu above the unchanged 1.05 pu limit.',13)
    save('V1_921_CELL_NODE_PHASE_SLOT_MAP.svg',body,170+len(bad)*23)
    old_cells=np.argwhere((baseline<.95)|(baseline>1.05))
    body=head+text(40,88,'The original 19 cells alone are an insufficient physical acceptance test.',17)
    for row,(slot,node) in enumerate(old_cells):
        yy=130+row*27;body+=text(20,yy+5,f's{slot:02d} {nodes[node]}',12)
        for value,color in ((baseline[slot,node],'#2563eb'),(v[slot,node],'#ea580c')):
            xx=220+(value-.95)/.115*780
            body+=f'<circle cx="{xx:.3f}" cy="{yy}" r="4" fill="{color}"/>'
        body+=text(1020,yy+4,f'{baseline[slot,node]:.6f} / {v[slot,node]:.6f}',11)
    xx=220+.1/.115*780;body+=line(xx,110,xx,660,'#dc2626',1.5)
    body+=text(220,700,'Blue: OFF; orange: V1 ON. Column shows original voltage / final voltage. Red line: 1.05 pu.',13)
    save('V1_ORIGINAL19_BEFORE_AFTER.svg',body,720)
    body=head+text(40,87,'Maximum phase apparent utilization includes positive converter losses. Required usable reserve: >=1.5.',15)
    for index,row in enumerate(phases):
        x=60+index*10;usage=float(row['max_converter_apparent_kva'])/float(row['phase_nameplate_kva'])
        height=usage*370
        body+=f'<rect x="{x}" y="{510-height:.3f}" width="8" height="{height:.3f}" fill="{"#dc2626" if usage>.6 else "#2563eb"}"/>'
        if index%3==0:body+=f'<text transform="translate({x+3},530) rotate(65)" font-size="9">{html.escape(row["device_id"])}</text>'
    body+=line(50,510-.6*370,1160,510-.6*370,'#dc2626',1.5)
    body+=text(40,675,'108 phase modules. Red threshold: 0.9 usable rating / 1.5 safety factor = 0.60 nameplate utilization.',13)
    save('V1_PHASE_APPARENT_RESERVE_SHORTFALL.svg',body,700)
    receipt=dict(schema='V42_DSTATCOM_PRESERVED_FAILURE_REPRODUCIBLE_SVG_V1',
        scope='FAILED_V1_DIAGNOSIS_NOT_24_PCC_APPROVED_DESIGN',Native_calls=0,DSS_calls=0,
        source_SHA=on_receipt['source_SHA'],scenario_SHA=on_receipt['scenario_SHA'],
        raw_sources=[record(p) for p in sources],script=record(Path(__file__)),
        figures=[record(p) for p in sorted(OUT.glob('*.svg'))])
    (OUT/'FIGURE_RECEIPTS.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
    print(json.dumps({'figures':len(receipt['figures']),'voltage_cells':int(((v<.95)|(v>1.05)).sum()),'Native':0,'DSS':0}))

if __name__=='__main__':main()
