"""Independent Source18r snapshot projection and numerical global-bound audit.

Does not import builders, the grid oracle, Gurobi, or any optimizer. Original
stored binary64 coefficients are interpreted exactly as Fractions. Exact
projection/row proofs are distinct from the solver's numerical MIP bound
contract; an exact rational branch-and-bound certificate is not claimed.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from fractions import Fraction as F
import gc
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import time
import traceback
import zipfile
import numpy as np
from scipy import sparse

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.critical_grid_cg.verify import read,write,sha,npz,require,canonical_data,axis,digests,upward,dyadic

OUT=ROOT/'docs/v42_b2_time_decomposed_global_lb'
OLD=ROOT/'docs/v42_physical_global_lb_pilot'
SOURCE=Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output')
SOURCE18R='497609b46faa14ea7e32a9483a333ab32fd264ef'
PARENT='40ab888b884255e76fd6c89fd01933570b60c242'
CASE='34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292'
OLD_LB=.46498486997548166
UB=.6760534504652341
SECURITY={'line_thermal_face','transformer_kVA','NormalAmps','voltage_upper','voltage_lower'}
GATES={'connected_Pch','connected_Pdis','no_simultaneous_charge','no_simultaneous_discharge','connected_Qmax','connected_Qmin','PCS16'}


def gzread(path):
    with gzip.open(path,'rt',encoding='utf-8') as stream:return json.load(stream)


def row_sha(row):
    packet={'original_row':row['original_row'],'name':row['name'],'sense':row['sense'],
            'rhs_hex':row['rhs_hex'],'terms':row['terms']}
    return hashlib.sha256(json.dumps(packet,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class OriginalRows:
    """Independent selective CSR access; no Full96 CSR/model reconstruction."""
    def __init__(self):
        inherited=read(OLD/'NATIVE0.json');proof=read(OLD/'INDEPENDENT_NATIVE0.json')
        require(inherited['PASS'] and proof['PASS'] and proof['base_commit']==SOURCE18R and inherited['case_sha']==CASE,
                'LITERAL_SOURCE_CERTIFICATE_FAILED')
        self.temp=tempfile.TemporaryDirectory(prefix='v42_snapshot_independent_');self.maps={};self.sources={}
        for filename in ('FULL_A.npz','FULL_DATA.npz'):
            p=SOURCE/filename;digest=sha(p)
            require(digest==inherited['source_records'][str(p)],'FROZEN_ORIGINAL_SOURCE_BYTES_CHANGED:'+filename)
            self.sources[str(p)]=digest
            folder=Path(self.temp.name)/filename;folder.mkdir()
            with zipfile.ZipFile(p) as archive:
                for member in archive.infolist():
                    require(Path(member.filename).name==member.filename and member.filename.endswith('.npy'),'UNSAFE_NPZ_MEMBER')
                    target=folder/member.filename
                    with archive.open(member) as stream,target.open('wb') as result:shutil.copyfileobj(stream,result,1024*1024)
                    self.maps[member.filename[:-4]]=np.load(target,mmap_mode='r',allow_pickle=False)
        require(tuple(self.maps['shape'])==(1130336,344967) and bytes(self.maps['format'])==b'csr','ORIGINAL_MATRIX_DIMENSIONS_CHANGED')
        obj=np.flatnonzero(self.maps['objective'])
        require(len(obj)==1 and self.maps['names'][obj[0]]=='rho_max' and self.maps['objective'][obj[0]]==1 and self.maps['constant']==0,
                'ORIGINAL_RHO_OBJECTIVE_CHANGED')
        self.rho=int(obj[0]);require(self.maps['lower'][self.rho]==0 and self.maps['upper'][self.rho]==1,'ORIGINAL_RHO_BOX_CHANGED')

    def row(self,r):
        r=int(r);lo,hi=self.maps['indptr'][r:r+2]
        return {'original_row':r,'name':str(self.maps['row_names'][r]),'sense':str(self.maps['sense'][r]),
                'rhs_hex':float(self.maps['rhs'][r]).hex(),
                'terms':[[int(c),float(v).hex()] for c,v in zip(self.maps['indices'][lo:hi],self.maps['data'][lo:hi])]}

    def close(self):
        for a in self.maps.values():
            mm=getattr(a,'_mmap',None)
            if mm is not None:mm.close()
        self.maps.clear();self.temp.cleanup();gc.collect()


def grid_exact(out):
    """Re-derive every original-slot inequality from independently read rows."""
    slot=int(out.name.replace('slot',''));raw=gzread(out/'GRID_RAW_CLOSURE.json.gz');exact=gzread(out/'GRID_EXACT.json.gz')
    authority=read(out/'GRID_AUTHORITY.json')
    require(raw['source']==exact['source']==SOURCE18R and raw['case_sha']==exact['case_sha']==CASE and
            raw['slot']==exact['slot']==slot and exact['parent']==PARENT,'GRID_SOURCE_CASE_OR_SLOT_CHANGED')
    for name,digest in authority['evidence'].items():require(sha(out/name)==digest,'GRID_GENERATOR_EVIDENCE_CHANGED')
    source=OriginalRows()
    try:
        require(source.sources==raw['source_files']==exact['source_files'],'GRID_SOURCE_FILE_SHA_AUTHORITY_CHANGED')
        columns={int(c):p for c,p in raw['columns'].items()};rows={r['original_row']:r for r in raw['rows']}
        require(len(rows)==len(raw['rows']),'RAW_CLOSURE_DUPLICATE_ROW')
        original_security=[]
        for r,label in enumerate(source.maps['row_names']):
            fam,coords=axis(label)
            if fam in SECURITY and int(coords[0])==slot:original_security.append(r)
        require(original_security==raw['original_security_rows'] and len(original_security)==8485,
                'ORIGINAL_SLOT_SECURITY_COVER_INCOMPLETE')
        helpers={};helper_count=Counter()
        for rid,row in rows.items():
            original=source.row(rid)
            require({k:row[k] for k in original}==original and row['source_row_sha256']==row_sha(original),
                    'RAW_SOURCE_ROW_TAMPERED:'+str(rid))
            family,coords=axis(row['name'])
            if family not in SECURITY:
                require(row['sense']=='=' and family.endswith('_binding') and family.startswith(('injection_','response_')),
                        'UNKNOWN_OR_NONEQUALITY_GRID_HELPER')
                pivots=[int(c) for c,h in row['terms'] if float.fromhex(h)==1. and axis(columns[int(c)]['name'])[0]+'_binding'==family]
                require(len(pivots)==1 and pivots[0] not in helpers,'HELPER_PIVOT_NOT_UNIQUE_POSITIVE_ONE')
                pivot=pivots[0];pivot_coords=axis(columns[pivot]['name'])[1]
                require(not coords or pivot_coords==coords,'HELPER_AXIS_MISMATCH')
                if family in ('injection_P_binding','injection_Q_binding'):
                    require(float.fromhex(row['rhs_hex'])==0.,'INJECTION_NONZERO_CONSTANT')
                    allowed={'Pch','Pdis'} if family=='injection_P_binding' else {'Q'}
                    for c,h in row['terms']:
                        if int(c)==pivot:continue
                        fam,parts=axis(columns[int(c)]['name']);v=float.fromhex(h)
                        require(fam in allowed and parts[1:]==pivot_coords and v==(1. if fam=='Pch' else -1.),'INJECTION_PQ_SIGN_OR_AXIS_CHANGED')
                helpers[pivot]=rid;helper_count[family]+=1
        for c,packet in columns.items():
            expected={'name':str(source.maps['names'][c]),'lower_hex':float(source.maps['lower'][c]).hex(),
                      'upper_hex':float(source.maps['upper'][c]).hex(),'type':str(source.maps['types'][c]),
                      'objective_hex':float(source.maps['objective'][c]).hex()}
            require(packet==expected,'RAW_COLUMN_DOMAIN_TAMPERED:'+str(c))
        cache={}
        def expand(c,visiting=()):
            if c in cache:return cache[c]
            require(c not in visiting,'HELPER_CYCLE')
            if c not in helpers:
                fam,parts=axis(columns[c]['name'])
                require(fam in ('Pch','Pdis','Q') or columns[c]['name']=='rho_max','NONPHYSICAL_HELPER_LEAF')
                if fam!='rho_max':require(int(parts[2])==slot,'GRID_CROSS_TIME_LEAF')
                answer=(F(0),{c:F(1)},set())
            else:
                r=helpers[c];row=rows[r];constant=F(float.fromhex(row['rhs_hex']));terms=defaultdict(F);used={r}
                for j,h in row['terms']:
                    j=int(j)
                    if j==c:continue
                    k,p,u=expand(j,visiting+(c,));co=-F(float.fromhex(h));constant+=co*k;used|=u
                    for leaf,value in p.items():terms[leaf]+=co*value
                answer=(constant,{j:v for j,v in terms.items() if v},used)
            cache[c]=answer;return answer
        rederived=[];total=0
        require(len(exact['rows'])==8485,'GRID_EXACT_ROW_COUNT_CHANGED')
        for record in exact['rows']:
            rid=record['original_row'];row=rows[rid];sign=F(1 if row['sense']=='<' else -1)
            require(rid in original_security and row['sense'] in ('<','>'),'GRID_SECURITY_SENSE_OR_ID_CHANGED')
            constant=F(0);terms=defaultdict(F);used=set()
            for c,h in row['terms']:
                offset,pieces,deps=expand(int(c));v=sign*F(float.fromhex(h));constant+=v*offset;used|=deps
                for j,value in pieces.items():terms[j]+=v*value
            terms={j:v for j,v in terms.items() if v};rhs=sign*F(float.fromhex(row['rhs_hex']))-constant
            named={columns[c]['name']:v for c,v in terms.items()};error=F(0);native={}
            for c,v in terms.items():
                lower=F(float.fromhex(columns[c]['lower_hex']));upper=F(float.fromhex(columns[c]['upper_hex']))
                cv=float(v);require(math.isfinite(cv) and cv!=0,'GRID_COEFFICIENT_DROPPED')
                error+=max((F(cv)-v)*lower,(F(cv)-v)*upper);native[columns[c]['name']]=cv
            require(record['name']==row['name'] and record['original_sense']==row['sense'] and
                    record['original_rhs_hex']==row['rhs_hex'] and record['source_row_sha256']==row_sha(row),
                    'GRID_ORIGINAL_ROW_AUTHORITY_CHANGED')
            require({n:F(v) for n,v in record['coeff'].items()}==named and F(record['rhs'])==rhs and
                    F(record['eliminated_constant'])==constant and record['helper_rows']==sorted(used) and record['sense']=='<',
                    'GRID_EXACT_ELIMINATION_CHANGED')
            require(record['native_coeff']==native and record['native_rhs']==upward(rhs+error) and
                    F(record['rounding_error'])==error and F(record['rhs_outward_extra'])==F(record['native_rhs'])-rhs-error,
                    'GRID_OUTWARD_ROUNDING_CHANGED')
            total+=len(named);rederived.append({'original_row':rid,'name':row['name'],'rhs':rhs,'coeff':named})
        require(total==exact['nnz'],'GRID_ELIMINATED_NNZ_CENSUS_CHANGED')
        family_census=dict(Counter(axis(rows[r]['name'])[0] for r in original_security))
        require(family_census==exact['original_grid_family_counts'],'GRID_FAMILY_CENSUS_CHANGED')
        return {'PASS':True,'slot':slot,'rows':8485,'eliminated_nnz':total,'literal_closure_rows':len(rows),
                'literal_closure_nnz':sum(len(r['terms']) for r in rows.values()),'helper_families':dict(helper_count),
                'family_counts':family_census,'source_files':source.sources,'all_original_security_rows_retained':True,
                'no_cross_time_security_leaves':True,'all_helper_injection_response_correction_constants_exact':True,
                'minimal_outward_rounding_verified':True,'rho_original_objective_and_box':True},raw,exact
    finally:source.close()


def replay(A,d,x):
    delta=A@x-d['rhs'];errors=np.where(d['senses']=='=',abs(delta),np.where(d['senses']=='<',delta,-delta))
    binary=np.flatnonzero(d['vtypes']=='B')
    return {'max_row_violation':max(0.,float(errors.max(initial=0.))),
            'max_box_violation':max(0.,float((d['lb']-x).max(initial=0.)),float((x-d['ub']).max(initial=0.))),
            'max_integer_error':float(abs(x[binary]-np.rint(x[binary])).max(initial=0.)),
            'objective':float(d['c']@x+float(d['constant']))}


def physical_rederive(slot):
    """Original one-path proof and literal immediate rows, independent producer."""
    inherited=read(OLD/'NATIVE0.json');prior=read(OLD/'INDEPENDENT_NATIVE0.json');old_index=read(OLD/'EVIDENCE_INDEX.json')['files']
    require(prior['PASS'] and prior['all_single_owner_physical_rows_bounds_and_integer_types_retained'],'LITERAL_UNIT_SLICE_PROOF_FAILED')
    identity=SOURCE/'SCIENTIFIC_CASE_IDENTITY.json'
    require(sha(identity)==inherited['source_records'][str(identity)],'ORIGINAL_ROUTE_DOMAIN_BYTES_CHANGED')
    domain=read(identity)['physical_prescreen_authority']['proof'];graph=domain['arcs'];expected_rows=[];boxes={};starts={};units=[]
    for unit in ('MESS01','MESS02','MESS03','MESS04'):
        spec=inherited['models'][unit]
        for suffix,key in (('A','matrix_sha'),('DATA','data_sha'),('AXES','axes_sha')):
            require(sha(OLD/f'UNIT_{unit}_{suffix}.npz')==spec[key],'ORIGINAL_LITERAL_UNIT_BYTES_CHANGED')
        A=sparse.load_npz(OLD/f'UNIT_{unit}_A.npz').tocsr();d=canonical_data(npz(OLD/f'UNIT_{unit}_DATA.npz'))
        axes=npz(OLD/f'UNIT_{unit}_AXES.npz');startfile=OLD/f'UNIT_{unit}_START.npz'
        require(sha(startfile)==old_index[startfile.name]['sha256'],'ORIGINAL_U4_UNIT_START_BYTES_CHANGED')
        x=npz(startfile)['point'];names=list(map(str,d['names']))
        stay={};arc={};outgoing=defaultdict(dict);incoming=defaultdict(dict);terminal={}
        for c,n in enumerate(names):
            fam,coords=axis(n)
            if fam!='arc':continue
            k=int(coords[1]);origin,depart,dest,end,route=graph[k];arc[k]=c
            require(depart<end and d['vtypes'][c]=='B' and d['lb'][c]==0 and d['ub'][c]==1,'ORIGINAL_ARC_NOT_BINARY_STRICT_TIME_DAG')
            outgoing[origin,depart][c]=F(1)
            if end<96:incoming[dest,end][c]=F(1)
            else:terminal[c]=F(1)
            if route is None and depart==slot:
                require(origin==dest and end==depart+1,'ORIGINAL_STAY_SEMANTICS_CHANGED');stay[origin]=c
        unit_spec=next(u for u in domain['units'] if u['mess']==unit)
        require(set(arc)==set(unit_spec['retained_arc_indices']),'ORIGINAL_ARC_COVER_CHANGED')
        signatures={}
        for node in set(outgoing)|set(incoming):
            terms=defaultdict(F,outgoing[node])
            for c,v in incoming[node].items():terms[c]-=v
            terms={c:v for c,v in terms.items() if v}
            if terms:signatures[tuple(sorted(terms.items()))]=F(int(node==(unit_spec['origin'],0)))
        flow_seen=set();terminal_seen=0;count=Counter()
        for r,label in enumerate(d['row_names']):
            fam=axis(label)[0]
            if fam not in GATES|{'flow','terminal_location'}:continue
            lo,hi=A.indptr[r:r+2];coeff={int(c):F(float(v)) for c,v in zip(A.indices[lo:hi],A.data[lo:hi])}
            if fam=='flow':
                signature=tuple(sorted(coeff.items()))
                require(signature in signatures and d['senses'][r]=='=' and F(float(d['rhs'][r]))==signatures[signature] and signature not in flow_seen,
                        'ORIGINAL_ONE_PATH_INCIDENCE_PROOF_FAILED')
                flow_seen.add(signature);continue
            if fam=='terminal_location':
                require(coeff==terminal and d['senses'][r]=='=' and d['rhs'][r]==1,'ORIGINAL_PATH_TERMINAL_CHANGED');terminal_seen+=1;continue
            powers=[c for c in coeff if axis(names[c])[0] in ('Pch','Pdis','Q')]
            require(powers,'ORIGINAL_IMMEDIATE_ROW_WITHOUT_POWER')
            times={int(axis(names[c])[1][2]) for c in powers};require(len(times)==1,'ORIGINAL_IMMEDIATE_ROW_CROSSES_TIME')
            if next(iter(times))!=slot:continue
            named={}
            for c,v in coeff.items():
                af,parts=axis(names[c])
                if af=='arc':
                    require(c in stay.values(),'IMMEDIATE_POWER_GATING_NOT_ORIGINAL_STAY')
                    k=int(parts[1]);site=graph[k][0];n=f'z[{unit},{site},{slot}]'
                else:n=names[c]
                named[n]=v
            expected_rows.append({'family':fam,'unit':unit,'original_row':int(axes['rows'][r]),'sense':str(d['senses'][r]),
                                  'rhs':F(float(d['rhs'][r])),'coeff':named});count[fam]+=1
        require(flow_seen==set(signatures) and terminal_seen==1,'ORIGINAL_ONE_PATH_FLOW_COVER_INCOMPLETE')
        sites=[]
        for c,n in enumerate(names):
            fam,parts=axis(n)
            if fam in ('Pch','Pdis','Q') and int(parts[2])==slot:
                boxes[n]=(float(d['lb'][c]),float(d['ub'][c]),str(d['vtypes'][c]));starts[n]=float(x[c])
                if fam=='Pch':sites.append(parts[1])
            if fam=='charge_mode' and int(parts[1])==slot:
                require(d['vtypes'][c]=='B' and d['lb'][c]==0 and d['ub'][c]==1,'ORIGINAL_MODE_BINARY_BOX_CHANGED')
                boxes[n]=(0.,1.,'B');starts[n]=float(x[c])
        require(set(sites)==set(stay),'ORIGINAL_AVAILABLE_POWER_SITE_AND_STAY_COVER_MISMATCH')
        for site,c in stay.items():
            n=f'z[{unit},{site},{slot}]';boxes[n]=(0.,1.,'B');starts[n]=float(x[c])
        expected_rows.append({'family':'snapshot_one_location','unit':unit,'original_row':None,'sense':'<','rhs':F(1),
                              'coeff':{f'z[{unit},{s},{slot}]':F(1) for s in sorted(sites)}})
        require(count==Counter({f:len(sites)*(16 if f=='PCS16' else 1) for f in GATES}),'IMMEDIATE_GATE_OR_PCS16_COVER_CHANGED')
        units.append({'unit':unit,'sites':sorted(sites),'location_binary':len(sites),'mode_binary':1,
                      'original_one_path_flow_rows_checked':len(flow_seen),'original_integer_arcs_checked':len(arc),'immediate_rows':sum(count.values()),
                      'all_zero_location_is_allowed':True,'immediate_row_families':dict(count)})
        del A,d,x,axes;gc.collect()
    return expected_rows,boxes,starts,units


def native0(out):
    started=time.perf_counter();slot=int(out.name.replace('slot',''))
    require(slot in (75,82,94),'UNREGISTERED_SNAPSHOT_SLOT')
    grid,raw,exact=grid_exact(out);physical,boxes,starts,units=physical_rederive(slot)
    A=sparse.load_npz(out/'SNAP_A.npz').tocsr();rawdata=npz(out/'SNAP_DATA.npz');d=canonical_data(rawdata)
    require(A.shape==(len(d['rhs']),len(d['names'])) and np.all(np.isin(d['vtypes'],['B','C'])),'SNAPSHOT_AXES_OR_TYPES_INVALID')
    require(len(set(map(str,d['names'])))==A.shape[1],'DUPLICATE_SNAPSHOT_COLUMN')
    lookup={str(n):c for c,n in enumerate(d['names'])}
    # The builder chooses exact helper lifting rather than dense materialization.
    rawcolumns={int(c):p for c,p in raw['columns'].items()}
    for c,p in rawcolumns.items():
        n=p['name'];lo=float.fromhex(p['lower_hex']);hi=float.fromhex(p['upper_hex']);ty=p['type']
        if n in boxes:require(boxes[n]==(lo,hi,ty),'GRID_AND_PHYSICS_SOURCE_BOX_CONFLICT')
        else:boxes[n]=(lo,hi,ty)
    require(set(lookup)==set(boxes),'SNAPSHOT_COLUMN_OR_AVAILABLE_SITE_COVER_CHANGED')
    for n,(lo,hi,ty) in boxes.items():
        c=lookup[n];require(d['lb'][c]==lo and d['ub'][c]==hi and d['vtypes'][c]==ty,'SNAPSHOT_SOURCE_BOUND_OR_TYPE_CHANGED:'+n)
    rho=lookup['rho_max']
    require(d['c'][rho]==1 and np.count_nonzero(d['c'])==1 and float(d['constant'])==0 and d['lb'][rho]==0 and d['ub'][rho]==1,
            'SNAPSHOT_OBJECTIVE_OR_RHO_BOX_CHANGED')
    expected=[]
    for row in physical:
        expected.append((row['sense'],float(row['rhs']),{lookup[n]:float(v) for n,v in row['coeff'].items()}))
    for row in raw['rows']:
        expected.append((row['sense'],float.fromhex(row['rhs_hex']),{lookup[rawcolumns[int(c)]['name']]:float.fromhex(h) for c,h in row['terms']}))
    signatures=Counter((sense,rhs,tuple(sorted(coeff.items()))) for sense,rhs,coeff in expected)
    actual=Counter()
    for r in range(A.shape[0]):
        lo,hi=A.indptr[r:r+2];actual[(str(d['senses'][r]),float(d['rhs'][r]),tuple(zip(map(int,A.indices[lo:hi]),map(float,A.data[lo:hi]))))]+=1
    require(signatures==actual,'SNAPSHOT_LITERAL_PHYSICS_OR_GRID_NATIVE_ROWS_CHANGED')
    # Independent exact lift of the original U4 physical point through helpers.
    definitions={}
    for row in raw['rows']:
        fam=axis(row['name'])[0]
        if not fam.endswith('_binding'):continue
        p=[int(c) for c,h in row['terms'] if float.fromhex(h)==1. and axis(rawcolumns[int(c)]['name'])[0]+'_binding'==fam]
        require(len(p)==1,'U4_HELPER_PIVOT_NOT_UNIQUE');definitions[rawcolumns[p[0]]['name']]=(p[0],row)
    starts['rho_max']=UB;exact_start={n:F(v) for n,v in starts.items()}
    def lift(n,seen=()):
        if n in exact_start:return exact_start[n]
        require(n in definitions and n not in seen,'U4_HELPER_LIFT_CYCLE_OR_UNKNOWN')
        pivot,row=definitions[n];value=F(float.fromhex(row['rhs_hex']))
        for c,h in row['terms']:
            if int(c)==pivot:continue
            value-=F(float.fromhex(h))*lift(rawcolumns[int(c)]['name'],seen+(n,))
        exact_start[n]=value;return value
    for n in definitions:starts[n]=float(lift(n))
    x=npz(out/'SNAP_START.npz')['x'];expectx=np.asarray([starts[str(n)] for n in d['names']])
    require(np.array_equal(x,expectx),'U4_SNAPSHOT_PROJECTION_COORDINATES_CHANGED')
    rep=replay(A,d,x);require(max(rep[k] for k in ('max_row_violation','max_box_violation','max_integer_error'))<=1e-7 and rep['objective']==UB,
                            'ORIGINAL_U4_SNAPSHOT_REPLAY_FAILED')
    # Also validate the separately computed eliminated form at the U4 point.
    worst=0.
    for row in exact['rows']:
        lhs=sum(float(F(v))*x[lookup[n]] for n,v in row['coeff'].items())
        worst=max(worst,lhs-float(F(row['rhs'])))
    require(worst<=1e-7,'ORIGINAL_U4_ELIMINATED_GRID_REPLAY_FAILED')
    matrix,domain=digests(A,rawdata);binary=int(np.count_nonzero(d['vtypes']=='B'))
    dimensions={'rows':A.shape[0],'columns':A.shape[1],'binary':binary,'nnz':int(A.nnz)}
    gates={'binary':binary<=256,'rows':A.shape[0]<=30000,'nnz':A.nnz<=500000}
    require(all(gates.values()),'SNAPSHOT_NATIVE_MODEL_SIZE_GATE_FAILED')
    files={n:sha(out/n) for n in ('SNAP_A.npz','SNAP_DATA.npz','SNAP_START.npz','PHYSICS_EXACT.json','GRID_EXACT.json.gz','GRID_RAW_CLOSURE.json.gz','GRID_AUTHORITY.json')}
    return {'PASS':True,'schema':'V42_TIME_SNAPSHOT_INDEPENDENT_NATIVE0_V1','phase':'Native0','slot':slot,
            'source18r':SOURCE18R,'PR214':PARENT,'case_sha':CASE,'Native_optimize_calls':0,'Gurobi_imported':False,
            'FULL_CSR_constructed':False,'FULL96_model_reconstructed':False,'FULL_projection_subset_snapshot':True,
            'all_original_available_power_sites_retained':True,'original_mode_binary_and_PQ_gates_PCS16_retained':True,
            'one_vehicle_one_location_integer':True,'all_zero_location_allowed':True,'same_original_rho_objective_and_bounds':True,
            'all_original_slot_security_retained':True,'representation':'Original exact injection/response helper equalities retained in Native; independent Fraction elimination certifies their physical projection.',
            'helper_original_unbounded_bounds_preserved':True,'helper_lift_native_rounding_error_exactly_zero':True,
            'units':units,'grid':grid,'dimensions':dimensions,'size_gates':gates,'U4_snapshot_replay':rep,
            'U4_eliminated_grid_max_violation':worst,'actual_matrix_sha256':matrix,'actual_domain_sha256':domain,
            'file_sha256':files,'source_files':grid['source_files'],
            'original_U4_unit_start_sha256':{u:sha(OLD/f'UNIT_{u}_START.npz') for u in ('MESS01','MESS02','MESS03','MESS04')},
            'exact_BB_trace_certificate':False,
            'proof':'Original nonnegative binary unit-flow on its strict-time DAG is one source-to-slot96 path. At t, original selected STAY arcs give z in{0,1} and sum(z)<=1. Every immediate P/Q/mode/PCS16 row is copied with STAY->z; original allzero transit stays imply P/Q=0. Dropping all inter-time route/SOC/travel/endpoint/rebound rows enlarges the projection. Exact original helper equalities and every original security row at t admit the copied original helper values, with unchanged rho and objective. Therefore min(snapshot rho)<=OPT_FULL. Only solver global lower bounds, never snapshot incumbents, are promoted.',
            'wall_seconds':time.perf_counter()-started}


def exact_snapshot_point(out,d,x):
    """Strict feasible rational point; no optimization or solver bound reuse.

The repair keeps a verified binary pattern, clamps disallowed/tiny power to
zero, and scales each site's P/Q uniformly if an exact PCS facet needs it.
Every original non-rho security row must then hold exactly. An exact rho
interval is derived from original source rows and helper values. Failure is
preserved, and never turned into an upper-bound/impossibility certificate.
"""
    packet=read(out/'PHYSICS_EXACT.json');raw=gzread(out/'GRID_RAW_CLOSURE.json.gz')
    cols={int(c):p for c,p in raw['columns'].items()};rho=next(c for c,p in cols.items() if p['name']=='rho_max')
    physical_names={str(n):c for c,n in enumerate(d['names']) if axis(n)[0] in ('z','charge_mode','Pch','Pdis','Q')}
    values={n:F(float(x[c])) for n,c in physical_names.items()}
    corrections=[]
    for n,c in physical_names.items():
        fam,coords=axis(n)
        if fam in ('z','charge_mode'):
            require(abs(float(values[n])-round(float(values[n])))<=1e-7,'EXACT_POINT_BINARY_PATTERN_NOT_VALID')
            v=F(round(float(values[n])))
        else:
            lo=F(float(d['lb'][c]));hi=F(float(d['ub'][c]));v=min(hi,max(lo,values[n]))
            unit,site,t=coords;z=values[f'z[{unit},{site},{t}]'];mode=values[f'charge_mode[{unit},{t}]']
            if round(float(z))==0 or (fam=='Pch' and round(float(mode))==0) or (fam=='Pdis' and round(float(mode))==1):v=F(0)
        if v!=values[n]:corrections.append({'name':n,'before':str(values[n]),'after':str(v)})
        values[n]=v
    # Powers are grouped by their actual original unit/site/slot coordinates.
    grouped=defaultdict(list)
    for n in values:
        if axis(n)[0] in ('Pch','Pdis','Q'):grouped[tuple(axis(n)[1])].append(n)
    scales={key:F(1) for key in grouped}
    for r in packet['rows']:
        if r['family']!='PCS16':continue
        terms={n:F(v) for n,v in r['coeff'].items()};p=[n for n in terms if axis(n)[0] in ('Pch','Pdis','Q')]
        require(p,'EXACT_PCS_FACET_HAS_NO_POWER');key=tuple(axis(p[0])[1])
        require(all(tuple(axis(n)[1])==key for n in p),'EXACT_PCS_CROSSES_SITE')
        cap=F(r['rhs'])-sum((v*values[n] for n,v in terms.items() if n not in p),F(0))
        dot=sum((terms[n]*values[n] for n in p),F(0));require(cap>=0,'EXACT_PCS_BINARY_CAP_NEGATIVE')
        if dot>cap:scales[key]=min(scales[key],cap/dot)
    for key,scale in scales.items():
        if scale<1:
            for n in grouped[key]:values[n]*=scale
    physics_violations=[]
    for row in packet['rows']:
        lhs=sum((F(v)*values[n] for n,v in row['coeff'].items()),F(0));rhs=F(row['rhs']);sense=row['sense']
        error=abs(lhs-rhs) if sense=='=' else lhs-rhs if sense=='<' else rhs-lhs
        if error>0:physics_violations.append({'name':row['name'],'exact_violation':str(error)})
    if physics_violations:
        return {'PASS':False,'reason':'STRICT_RATIONAL_PHYSICS_REPAIR_FAILED','violations':physics_violations[:16]},None
    definitions={};security=[]
    for r in raw['rows']:
        fam=axis(r['name'])[0]
        if fam in SECURITY:security.append(r);continue
        pivots=[int(c) for c,h in r['terms'] if float.fromhex(h)==1. and axis(cols[int(c)]['name'])[0]+'_binding'==fam]
        require(len(pivots)==1,'EXACT_POINT_HELPER_PIVOT_NOT_UNIQUE');definitions[pivots[0]]=r
        if any(int(c)==rho for c,h in r['terms']):
            return {'PASS':False,'reason':'EXACT_POINT_HELPER_DEPENDS_ON_RHO_NOT_IMPLEMENTED'},None
    column_values={c:values[p['name']] for c,p in cols.items() if p['name'] in values};column_values[rho]=F(0)
    def evaluate(c,seen=()):
        if c in column_values:return column_values[c]
        require(c in definitions and c not in seen,'EXACT_POINT_HELPER_CYCLE_OR_UNDEFINED')
        r=definitions[c];value=F(float.fromhex(r['rhs_hex']))
        for j,h in r['terms']:
            if int(j)!=c:value-=F(float.fromhex(h))*evaluate(int(j),seen+(c,))
        column_values[c]=value;return value
    for c in cols:evaluate(c)
    lower,upper=F(0),F(1);nonrho_bad=[];rho_lower_rows=[];rho_upper_rows=[]
    for r in security:
        sign=F(1 if r['sense']=='<' else -1);co=F(0);constant=F(0)
        for c,h in r['terms']:
            v=sign*F(float.fromhex(h))
            if int(c)==rho:co+=v
            else:constant+=v*column_values[int(c)]
        rhs=sign*F(float.fromhex(r['rhs_hex']))
        if co<0:
            demand=(constant-rhs)/(-co)
            if demand>lower:lower=demand;rho_lower_rows=[r['original_row']]
            elif demand==lower:rho_lower_rows.append(r['original_row'])
        elif co>0:
            limit=(rhs-constant)/co
            if limit<upper:upper=limit;rho_upper_rows=[r['original_row']]
            elif limit==upper:rho_upper_rows.append(r['original_row'])
        elif constant>rhs:nonrho_bad.append({'original_row':r['original_row'],'name':r['name'],'exact_violation':str(constant-rhs)})
    if nonrho_bad or lower>upper:
        return {'PASS':False,'reason':'STRICT_RATIONAL_GRID_REPAIR_FAILED','nonrho_violations':nonrho_bad[:16],
                'nonrho_violation_count':len(nonrho_bad),'rho_required_lower':str(lower),'rho_permitted_upper':str(upper),
                'integer_pattern_preserved':True,'physical_exact_feasibility':True},None
    column_values[rho]=lower
    # Every raw helper equality and grid inequality is checked strictly again.
    for r in raw['rows']:
        lhs=sum((F(float.fromhex(h))*column_values[int(c)] for c,h in r['terms']),F(0));rhs=F(float.fromhex(r['rhs_hex']))
        require(lhs==rhs if r['sense']=='=' else lhs<=rhs if r['sense']=='<' else lhs>=rhs,'STRICT_EXACT_POINT_RAW_ROW_FAILED')
    for n,c in physical_names.items():
        require(F(float(d['lb'][c]))<=values[n]<=F(float(d['ub'][c])),'STRICT_EXACT_POINT_BOX_FAILED')
    # Final strict check uses the independently certified actual CSR, so a
    # malformed convenience physics packet could never certify a false point.
    allvalues=dict(values);allvalues.update({p['name']:column_values[c] for c,p in cols.items()})
    A=sparse.load_npz(out/'SNAP_A.npz').tocsr()
    actual_violation=[]
    for r in range(A.shape[0]):
        lo,hi=A.indptr[r:r+2]
        lhs=sum((F(float(v))*allvalues[str(d['names'][c])] for c,v in zip(A.indices[lo:hi],A.data[lo:hi])),F(0))
        rhs=F(float(d['rhs'][r]));sense=d['senses'][r]
        error=abs(lhs-rhs) if sense=='=' else lhs-rhs if sense=='<' else rhs-lhs
        if error>0:actual_violation.append({'row':r,'name':str(d['row_names'][r]),'exact_violation':str(error)})
    if actual_violation:
        return {'PASS':False,'reason':'STRICT_ACTUAL_CERTIFIED_CSR_POINT_CHECK_FAILED','violations':actual_violation[:16]},None
    helpers={p['name']:str(column_values[c]) for c,p in cols.items() if c in definitions}
    receipt={'PASS':True,'schema':'V42_SNAPSHOT_EXACT_FEASIBLE_RATIONAL_POINT_V1','source18r':SOURCE18R,'case_sha':CASE,
             'objective_exact':str(lower),'objective_upper_outward':upward(lower),'rho_permitted_upper':str(upper),
             'rho_active_lower_original_rows':rho_lower_rows,'rho_active_upper_original_rows':rho_upper_rows,
             'physical_rows_checked':len(packet['rows']),'original_grid_rows_checked':len(security),'original_helper_equalities_checked':len(definitions),
             'actual_certified_CSR_rows_checked':A.shape[0],'actual_certified_CSR_NNZ_checked':int(A.nnz),
             'integer_location_mode_pattern_preserved':True,'all_constraints_checked_as_exact_Fractions':True,
             'power_clamp_corrections':corrections,'site_uniform_PCS_scales':{'/'.join(k):str(v) for k,v in scales.items() if v<1},
             'snapshot_optimum_upper_bound_only':True,'is_original_FULL_UB':False,'Actual_AC_PASS':False}
    point={'physical_values':{n:str(v) for n,v in sorted(values.items())},'rho_max':str(lower),'original_helpers':helpers}
    write(out/'EXACT_SNAPSHOT_FEASIBLE_POINT.json',point);receipt['point_sha256']=sha(out/'EXACT_SNAPSHOT_FEASIBLE_POINT.json')
    return receipt,lower


def final(out):
    started=time.perf_counter();zero=read(out/'INDEPENDENT_NATIVE0.json');build=read(out/'NATIVE0.json')
    require(zero['PASS'] and build['PASS'] and zero['FULL_projection_subset_snapshot'] and zero['source18r']==SOURCE18R and zero['case_sha']==CASE,
            'SNAPSHOT_INDEPENDENT_NATIVE0_FAILED')
    require(zero['actual_matrix_sha256']==build['matrix_sha'] and zero['actual_domain_sha256']==build['domain_sha'] and zero['file_sha256']==build['file_sha256'],
            'BUILDER_INDEPENDENT_HASH_MISMATCH')
    for n,h in zero['file_sha256'].items():require(sha(out/n)==h,'POST_NATIVE_MODEL_ARTIFACT_CHANGED:'+n)
    for p,h in zero['source_files'].items():require(sha(p)==h,'POST_NATIVE_ORIGINAL_SOURCE_CHANGED:'+p)
    result=read(out/'RESULT.json');readback=read(out/'NATIVE_READBACK.json');latch=read(out/'PILOT_STARTED.json')
    params={'Threads':1,'TimeLimit':30.,'Method':1,'FeasibilityTol':1e-8,'OptimalityTol':1e-8,'IntFeasTol':1e-8,'MIPGap':1e-6}
    require(readback['PASS'] and all(readback['checks'].values()) and readback['parameters']==params and latch['parameters']==params,
            'ACTUAL_NATIVE_READBACK_OR_PARAMETERS_FAILED')
    require(readback['matrix_sha']==zero['actual_matrix_sha256'] and readback['domain_sha']==zero['actual_domain_sha256'] and latch['files']==zero['file_sha256'] and
            latch['independent_native0_sha256']==sha(out/'INDEPENDENT_NATIVE0.json'),'NATIVE_READBACK_OR_LATCH_MODEL_IDENTITY_CHANGED')
    require(result['Native_optimize_calls']==latch['Native_optimize_calls']==1 and result['TimeLimit']==30 and result['Threads']==1 and result['slot']==zero['slot'],
            'NATIVE_BUDGET_OR_SLOT_CONTRACT_CHANGED')
    require(all(result[k]==0 for k in ('full_MILP_calls','campaign_calls','B1_launches')) and
            result['incumbent_is_original_FULL_UB'] is False and result['Actual_AC_PASS'] is False,'UNAUTHORIZED_SCOPE_OR_SNAPSHOT_INCUMBENT_PROMOTION')
    ledger=read(out.parent/'NATIVE_LEDGER.json');calls=ledger['calls'];snapshots=[c for c in calls if c['kind']=='SNAPSHOT']
    require(ledger['snapshot_maximum_calls']==3 and ledger['window_maximum_calls']==1 and ledger['maximum_requested_seconds']==210 and
            len(snapshots)<=3 and [c['slot'] for c in snapshots]==[75,82,94][:len(snapshots)] and all(c['TimeLimit']==30. for c in snapshots) and
            sum(c['TimeLimit'] for c in snapshots)<=90 and len(calls)<=4 and sum(c['TimeLimit'] for c in calls)<=210,'GLOBAL_NATIVE_LEDGER_BUDGET_INVALID')
    matches=[c for c in snapshots if c['slot']==zero['slot']]
    require(len(matches)==1 and Path(matches[0]['out']).resolve()==out.resolve(),'NATIVE_LEDGER_SLOT_LATCH_MISMATCH')
    require(read(out/'PRE_NATIVE_PEERS.json')['PASS'] and read(out/'MEMORY_RESOURCE_ADMISSION.json')['PASS'],'NATIVE_RESOURCE_ADMISSION_FAILED')
    A=sparse.load_npz(out/'SNAP_A.npz').tocsr();d=canonical_data(npz(out/'SNAP_DATA.npz'));matrix,domain=digests(A,npz(out/'SNAP_DATA.npz'))
    require(matrix==zero['actual_matrix_sha256'] and domain==zero['actual_domain_sha256'],'FINAL_STORED_MODEL_HASH_CHANGED')
    require((result['Rows'],result['Columns'],result['Binary'],result['NNZ'])==(A.shape[0],A.shape[1],int(np.count_nonzero(d['vtypes']=='B')),A.nnz),
            'NATIVE_DIMENSION_ATTRIBUTES_CHANGED')
    trace=read(out/'MEMORY_TRACE.json');samples=trace['samples']
    require(len(samples)>=2 and result['minimum_RAM_available']==min(s['system']['RAM_available'] for s in samples) and
            result['minimum_commit_available']==min(s['system']['Commit_available'] for s in samples) and
            result['peak_process_RSS_bytes']==max(s['Peak_RSS_bytes'] for s in samples) and
            result['peak_private_commit_bytes']==max(s['Peak_Private_Commit_bytes'] or s['Private_Commit_bytes'] for s in samples),
            'NATIVE_MEMORY_TRACE_SUMMARY_CHANGED')
    log=(out/'NATIVE.log').read_text(encoding='utf-8',errors='replace')
    numeric_failure=any(token.lower() in log.lower() for token in ('numerical trouble','out of memory','numeric error'))
    bound=result.get('ObjBound');value=result.get('ObjVal')
    candidate=(result['Status'] in (2,9) and bound is not None and math.isfinite(float(bound)) and abs(float(bound))<1e99 and
               result['optimize_error'] is None and not result['numeric_errors'] and not result['resource_stops'] and not result['memory_stops'] and not numeric_failure)
    incumbent_replay=None;strict=None;exact_upper=None
    if result['SolCount']>0:
        x=npz(out/'INCUMBENT.npz')['x'];incumbent_replay=replay(A,d,x)
        require(max(incumbent_replay[k] for k in ('max_row_violation','max_box_violation','max_integer_error'))<=1e-7 and
                abs(incumbent_replay['objective']-value)<=1e-9,'NUMERICAL_SNAPSHOT_INCUMBENT_REPLAY_FAILED')
        require(bound is None or bound<=value+1e-7,'SOLVER_GLOBAL_BOUND_EXCEEDS_INCUMBENT')
        strict,exact_upper=exact_snapshot_point(out,d,x)
    if candidate:
        require(-1e-8<=float(bound)<=UB+1e-7,'SOLVER_GLOBAL_BOUND_OUTSIDE_ORIGINAL_U4_REFERENCE')
    certified=float(bound) if candidate else None
    globalnew=max(OLD_LB,certified) if certified is not None else OLD_LB
    impossible=bool(strict and strict['PASS'] and exact_upper<=F(OLD_LB)+F(1,1000))
    integer_optimal=result['Status']==2
    root_observed=bool(result['root_log_messages'] or any(r['status']==2 for r in result['root_node_observations']))
    lp=result.get('LP_relaxation_log_objective')
    require(lp is None or (result['LP_relaxation_value_is_log_rounded'] and root_observed),'LP_RELAXATION_DIAGNOSTIC_SCOPE_CHANGED')
    return {'PASS':candidate,'schema':'V42_TIME_SNAPSHOT_INDEPENDENT_GLOBAL_BOUND_V1','phase':'Final','slot':zero['slot'],
            'source18r':SOURCE18R,'PR214':PARENT,'case_sha':CASE,'Certified_LB':certified,'certified_Global_LB':certified,
            'Global_LB_after_this_snapshot':globalnew,'global_gap_after_this_snapshot':(UB-globalnew)/UB,
            'solver_status':result['Status'],'ObjBound':bound,'ObjVal':value,'MILP_solver_global_bound_valid':candidate,
            'GlobalBound_source':'Gurobi numerical global MIP ObjBound after exact domain/CSR audit and fixed-parameter Native readback' if candidate else None,
            'incumbent_valid':incumbent_replay is not None,'incumbent_replay':incumbent_replay,
            'exact_snapshot_feasible_point_certificate':strict,'snapshot_material_impossible_from_incumbent':impossible,
            'exact_snapshot_optimum_upper_bound':None if exact_upper is None else str(exact_upper),
            'early_nonmaterial_scope':'Only this preregistered snapshot. Does not exclude any multi-period Window improvement.',
            'LP_relaxation_log_objective':lp,'LP_relaxation_diagnostic_only':True,'root_relaxation_observed':root_observed,
            'integer_optimal':integer_optimal,'root_presolve_completion_is_not_a_separate_LP_certificate':True,
            'Native_optimize_calls_audited':1,'full_MILP_calls':0,'B1_launches':0,
            'numeric_failure_in_log':numeric_failure,'exact_BB_trace_certificate':False,
            'exact_original_projection_and_helper_elimination_PASS':True,'snapshot_incumbent_promoted_as_global_LB':False,
            'snapshot_incumbent_is_original_FULL_UB':False,'Actual_AC_PASS':False,
            'native_latch_sha256':sha(out/'PILOT_STARTED.json'),'native_result_sha256':sha(out/'RESULT.json'),
            'independent_native0_sha256':sha(out/'INDEPENDENT_NATIVE0.json'),'wall_seconds':time.perf_counter()-started}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('native0','final','grid'),required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    try:
        if args.mode=='grid':value=grid_exact(args.out)[0]
        else:value=native0(args.out) if args.mode=='native0' else final(args.out)
        filename='INDEPENDENT_GRID.json' if args.mode=='grid' else 'INDEPENDENT_NATIVE0.json' if args.mode=='native0' else 'INDEPENDENT_CERTIFICATE.json'
        write(args.out/filename,value);print({'PASS':value['PASS'],'mode':args.mode,'slot':value.get('slot'),'dimensions':value.get('dimensions')})
    except Exception as error:
        value={'PASS':False,'phase':args.mode,'reason':str(error),'exception':traceback.format_exc(),'Native_optimize_calls':0,'Gurobi_imported':False}
        write(args.out/('INDEPENDENT_'+args.mode.upper()+'_FAILED.json'),value);raise
