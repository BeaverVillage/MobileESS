"""Past-only tail severity and shape analog memory."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dayahead.ml.faser_flex.signatures import batch_signature


@dataclass(frozen=True)
class TailAnalogLibrary:
    """Training-only P80+ signatures, severities, shapes, and immutable dates."""

    dates: np.ndarray
    representation: np.ndarray
    interval: np.ndarray
    normalized_severity: np.ndarray
    shapes: np.ndarray
    median: np.ndarray
    IQR: np.ndarray
    distance_median: float


@dataclass(frozen=True)
class AnalogResult:
    """Deterministic analog indices, weights, shrinkage, severity and shape."""

    indices: np.ndarray
    weights: np.ndarray
    lambda_analog: float
    normalized_severity: float | None
    shape: np.ndarray | None
    minimum_distance: float | None


def interval_and_severity(target: np.ndarray, thresholds: np.ndarray) -> tuple[np.ndarray,np.ndarray]:
    """Map P80+ training targets to interval identity and normalized severity."""

    u80,u90,u95=np.asarray(thresholds,float)[2:]
    interval=np.full(len(target),-1,int); severity=np.full(len(target),np.nan,float)
    first=(target>u80)&(target<=u90); second=(target>u90)&(target<=u95); third=target>u95
    interval[first]=0; severity[first]=(target[first]-u80)/max(u90-u80,1e-9)
    interval[second]=1; severity[second]=(target[second]-u90)/max(u95-u90,1e-9)
    interval[third]=2; severity[third]=np.log1p(target[third]-u95)
    return interval,severity


def representation(paths:np.ndarray,explicit:np.ndarray)->np.ndarray:
    """Return exact depth-2 log-signature plus explicit causal pressure features."""

    # Daily differences keep the signature compact while preserving seven-day order.
    daily=paths.reshape(len(paths),7,24,paths.shape[-1]).sum(axis=2)
    signature=batch_signature(daily,depth=2,log_signature=True)
    return np.column_stack((signature,explicit))


def build_library(dates:np.ndarray,paths:np.ndarray,explicit:np.ndarray,target:np.ndarray,thresholds:np.ndarray,shapes:np.ndarray)->TailAnalogLibrary:
    """Build a tail-only library from outer-training rows; body rows are excluded."""

    interval,severity=interval_and_severity(target,thresholds); tail=interval>=0
    raw=representation(paths[tail],explicit[tail]); median=np.median(raw,axis=0)
    iqr=np.maximum(np.quantile(raw,.75,axis=0)-np.quantile(raw,.25,axis=0),1e-6)
    scaled=(raw-median)/iqr
    if len(scaled)>1:
        distances=np.linalg.norm(scaled[:,None,:]-scaled[None,:,:],axis=2)
        distance_median=float(np.median(distances[np.triu_indices(len(scaled),1)]))
    else:
        distance_median=1.0
    return TailAnalogLibrary(np.asarray(dates)[tail],scaled,interval[tail],severity[tail],shapes[tail],median,iqr,max(distance_median,1e-6))


def retrieve(library:TailAnalogLibrary,date:str,path:np.ndarray,explicit:np.ndarray,interval:int,k:int,temperature:float,tau_A:float)->AnalogResult:
    """Retrieve only same-interval analogs strictly earlier than the forecast date."""

    eligible=(library.dates<date)&(library.interval==interval)
    indices=np.flatnonzero(eligible)
    if len(indices)==0:
        return AnalogResult(indices,np.zeros(0),0.0,None,None,None)
    query=(representation(path[None],explicit[None])[0]-library.median)/library.IQR
    distance=np.linalg.norm(library.representation[indices]-query,axis=1)
    order=np.argsort(distance,kind="stable")[:min(k,len(indices))]
    selected=indices[order]; selected_distance=distance[order]
    weight=np.exp(-(selected_distance-selected_distance.min())/max(temperature,1e-9)); weight/=weight.sum()
    effective=1.0/np.square(weight).sum(); minimum=float(selected_distance.min())
    shrinkage=effective/(effective+tau_A)*np.exp(-minimum/library.distance_median)
    severity=float(np.dot(weight,library.normalized_severity[selected]))
    shape=np.tensordot(weight,library.shapes[selected],axes=(0,0)); shape/=shape.sum()
    return AnalogResult(selected,weight,float(shrinkage),severity,shape,minimum)

