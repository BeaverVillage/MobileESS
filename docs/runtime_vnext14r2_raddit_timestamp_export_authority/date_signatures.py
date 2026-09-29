from common import *
h=pd.read_parquet(R1/'.local/HISTORIC_SHARED_METADATA.parquet')
m=pd.read_parquet(R1/'.local/HISTORIC_RAW_MEMBERSHIP_NEGATIVE_LEDGER.parquet').sort_values('historic_row')
member=m.embedding_count.notna().to_numpy();unique=m.embedding_count.eq(1).to_numpy();amb=member&~unique
names=['observed raw-member start_time envelope','observed raw-member end_time envelope','end calendar date >= first observed member end date']
rules=[r for r in pd.read_csv(ROOT/'SUBSET_FILTER_CANDIDATES.csv').to_dict('records') if r['rule'] not in names]
enrich=[r for r in pd.read_csv(ROOT/'SUBSET_MEMBERSHIP_ENRICHMENT.csv').to_dict('records') if r['rule'] not in names];details=[]
def add(name,keep,boundary):
    rules.append(dict(rule=name,historic_kept=int(keep.sum()),historic_removed=int((~keep).sum()),equals_embedding_count=int(keep.sum())==1780972,source_support='Observed date envelope; no source export query/manifest. Membership equality is diagnostic only.',membership_exact_match=bool(np.array_equal(keep,member)),status='DIAGNOSTIC_NOT_APPROVED'))
    for label,mask in [('UNIQUE_RAW',unique),('AMBIGUOUS_RAW',amb),('NO_RAW_MEMBER',~member)]:enrich.append(dict(rule=name,population=label,rows=int(mask.sum()),satisfying=int((keep&mask).sum()),fraction=float(keep[mask].mean())))
    details.append(dict(rule=name,boundary=boundary,raw_membership_equal=bool(np.array_equal(keep,member))))
for c in ['start_time','end_time']:
    lo=int(h.loc[member,c].min());hi=int(h.loc[member,c].max());add('observed raw-member '+c+' envelope',h[c].between(lo,hi).to_numpy(),dict(min=str(pd.Timestamp(lo,unit='us')),max=str(pd.Timestamp(hi,unit='us'))))
# Calendar-date signature, not truncation of the timestamps used in identity keys.
cut=pd.Timestamp(int(h.loc[member,'end_time'].min()),unit='us').normalize();cut_us=timestamp_us(cut)
add('end calendar date >= first observed member end date',h.end_time.ge(cut_us).to_numpy(),dict(first_end_date=str(cut.date()),note='Diagnostic cutoff derived once from member envelope, no threshold search. Not a source-backed export rule.'))
table('SUBSET_FILTER_CANDIDATES.csv',rules);table('SUBSET_MEMBERSHIP_ENRICHMENT.csv',enrich);write('DATE_MEMBERSHIP_SIGNATURES.json',details)
for r in rules[-3:]:print(json.dumps(clean(r)))
