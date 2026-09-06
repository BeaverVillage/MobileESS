"""Exact finite all-checkpoint domain, stored without its Cartesian expansion."""
from collections.abc import Sequence
from math import ceil
from dayahead.v40g.domain import Option,deviation
from .migration import BEGIN,END,placement_sites,checkpoints


class CompactChoices(Sequence):
    def __init__(self,row,initial,eligible,valid_cps,length):
        self.row=row;self.initial=tuple(initial);self.sites=tuple(eligible);self.length=length
        self.valid_checkpoints=tuple(valid_cps)
        self.cps=tuple(c for c in valid_cps if max(BEGIN+2,c)+length+1<END)
        self.routes=tuple((s,d) for s in self.initial for d in self.sites if s!=d)
        self.sources={d:tuple(sorted(s for s,dd in self.routes if dd==d)) for d in self.sites}
        self.nsource=next(len(v) for v in self.sources.values() if v)
        assert all(not v or len(v)==self.nsource for v in self.sources.values())
        self.pairs=tuple((g,c) for g in range(length+1,END-BEGIN) for c in self.cps if self.valid_gap(c,g))
        self.pair_index={v:i for i,v in enumerate(self.pairs)}
        self.prefix={};n=0
        for d in self.sites:
            self.prefix[d]=n;n+=int(d in self.initial)+len(self.sources[d])*len(self.pairs)
        self.count=n
        self.signature=(self.initial,self.sites,self.valid_checkpoints,length,row['start_slot'],row['end_slot'],row['AIDC_site'])
    @property
    def has_migrations(self):return bool(self.pairs and self.routes)
    def valid_gap(self,cp,gap):return max(BEGIN+2,cp)+self.length+1<=cp+gap<END
    def __len__(self):return self.count
    def __hash__(self):return hash(self.signature)
    def __eq__(self,other):return isinstance(other,CompactChoices) and self.signature==other.signature
    def make(self,source,destination,cp,gap):
        return Option(destination,self.row['start_slot'],self.row['end_slot']+gap,cp,
            cp+gap-self.length-1,cp+gap-1,source if self.row['state_at_issue']=='PENDING' and self.row['start_slot']>=BEGIN else '')
    def __iter__(self):
        for d in self.sites:
            if d in self.initial:yield Option(d,self.row['start_slot'],self.row['end_slot'])
            for gap,cp in self.pairs:
                for source in self.sources[d]:yield self.make(source,d,cp,gap)
    def __getitem__(self,index):
        if isinstance(index,slice):return tuple(self)[index]
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        for d in self.sites:
            offset=index-self.prefix[d];stay=int(d in self.initial);n=len(self.sources[d])*len(self.pairs)+stay
            if not 0<=offset<n:continue
            if stay and offset==0:return Option(d,self.row['start_slot'],self.row['end_slot'])
            pair,source_index=divmod(offset-stay,len(self.sources[d]));gap,cp=self.pairs[pair]
            return self.make(self.sources[d][source_index],d,cp,gap)
        raise IndexError(index)
    def index(self,opt,start=0,stop=None):
        d=opt.site
        if d not in self.sites:raise ValueError('UNKNOWN_DESTINATION')
        if not opt.migrated:
            if opt!=Option(d,self.row['start_slot'],self.row['end_slot']) or d not in self.initial:raise ValueError('INVALID_PLACEMENT')
            return self.prefix[d]
        source=opt.initial_site or self.row['AIDC_site'];gap=opt.transfer_end+1-opt.checkpoint
        if (gap,opt.checkpoint) not in self.pair_index or source not in self.sources[d]:raise ValueError('INVALID_MIGRATION_TUPLE')
        if opt!=self.make(source,d,opt.checkpoint,gap):raise ValueError('INVALID_MIGRATION_TIMING')
        return self.prefix[d]+int(d in self.initial)+len(self.sources[d])*self.pair_index[gap,opt.checkpoint]+self.sources[d].index(source)
    def __contains__(self,opt):
        try:self.index(opt);return True
        except (ValueError,AttributeError):return False


class Costs(Sequence):
    def __init__(self,row,choices):self.row=row;self.choices=choices
    def __len__(self):return len(self.choices)
    def __getitem__(self,index):return deviation(self.row,self.choices[index])
    def __hash__(self):return hash((self.choices,self.row['requested_GPU']))
    def __eq__(self,other):return isinstance(other,Costs) and self.choices==other.choices and self.row['requested_GPU']==other.row['requested_GPU']


def uniform_domain(row,capacity,wan,elapsed):
    initial=placement_sites(row,capacity)
    eligible=tuple(s for s in capacity.aidc_ids if capacity.site_capacity[s]>=row['requested_GPU'] and capacity.eligible_racks(s,row['requested_GPU']))
    cps=checkpoints(row,elapsed)
    if not cps or not eligible:return None
    lengths=set()
    for source in initial:
        for dest in eligible:
            if source==dest:continue
            rates={wan.path_capacity_bytes(source,dest,t) for t in range(96)}
            if len(rates)!=1 or min(rates)<=0:return None
            lengths.add(ceil(wan.payload_bytes(row['requested_GPU'])/next(iter(rates))))
    if len(lengths)!=1:return None
    choices=CompactChoices(row,initial,eligible,cps,next(iter(lengths)))
    return choices if choices.has_migrations else None


def metadata(opts):
    if isinstance(opts,CompactChoices):
        return dict(options=len(opts),migration_options=len(opts)-len(opts.initial),
            jobs_with_migration_options=True,jobs_with_spatial_options=len(opts.sites)>1,jobs_with_temporal_options=False)
    return dict(options=len(opts),migration_options=sum(o.migrated for o in opts),
        jobs_with_migration_options=any(o.migrated for o in opts),jobs_with_spatial_options=len({o.site for o in opts})>1,
        jobs_with_temporal_options=len({o.start for o in opts})>1)


def costs(row,opts):return Costs(row,opts) if isinstance(opts,CompactChoices) else tuple(deviation(row,o) for o in opts)
