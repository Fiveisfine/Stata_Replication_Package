"""Auditable Python HDFE estimator, calibrated to archived Stata outputs.

No claim of a new Stata execution. Singleton removal and absorbed degrees of
freedom use pyhdfe; inference uses cluster-robust covariance and t(G-1).
"""
import numpy as np
import pandas as pd
import pyhdfe
from scipy.linalg import qr
from scipy.stats import t


def fit(frame,y,x,fe,clusters=('firm_id',)):
    cols=list(dict.fromkeys([y]+x+fe+list(clusters)))
    work=frame.dropna(subset=cols).copy()
    n_input=len(work)
    ids=np.column_stack([pd.factorize(work[c],sort=False)[0] for c in fe])
    cids=np.column_stack([pd.factorize(work[c],sort=False)[0] for c in clusters])
    alg=pyhdfe.create(ids,cluster_ids=cids,drop_singletons=True,compute_degrees=True,options={'tol':1e-10})
    mat=alg.residualize(work[[y]+x].to_numpy(dtype=float))
    work=work.loc[~alg.singleton_indices].copy()
    yy=mat[:,0];xx=mat[:,1:]
    norms=np.linalg.norm(xx,axis=0);safe=np.maximum(norms,1e-100)
    original_norm=np.linalg.norm(frame.loc[work.index,x].to_numpy(dtype=float),axis=0)
    possible=np.flatnonzero(norms>1e-9*np.maximum(original_norm,1))
    _,rr,piv=qr((xx/safe)[:,possible],pivoting=True,mode='economic')
    rank=int(np.sum(np.abs(np.diag(rr))>1e-8));idx=sorted(possible[piv[:rank]]);omitted=[x[i] for i in range(len(x)) if i not in idx]
    xx=xx[:,idx];names=[x[i] for i in idx]
    beta=np.linalg.lstsq(xx,yy,rcond=1e-12)[0];resid=yy-xx@beta
    bread=np.linalg.pinv(xx.T@xx,rcond=1e-12)
    n=len(work);k=rank+alg.degrees
    def cov_for(values):
        codes,names_cluster=pd.factorize(values,sort=False);g=len(names_cluster)
        scores=np.zeros((g,rank));np.add.at(scores,codes,xx*resid[:,None])
        covariance=bread@(scores.T@scores)@bread
        return covariance*(g/(g-1))*((n-1)/(n-k)),g
    covariance,g=cov_for(work[clusters[0]])
    cluster_counts={clusters[0]:g}
    if len(clusters)==2:
        c2,g2=cov_for(work[clusters[1]])
        ci,gi=cov_for(pd.MultiIndex.from_frame(work[list(clusters)]))
        covariance=covariance+c2-ci;g=min(g,g2)
        # CGM may be indefinite in finite samples; retain and report, do not silently repair.
        cluster_counts.update({clusters[1]:g2,'intersection':gi})
    return {'beta':pd.Series(beta,index=names),'cov':pd.DataFrame(covariance,index=names,columns=names),'N':n,'N_input':n_input,'singletons_removed':n_input-n,'df_absorbed':alg.degrees,'df_resid_cluster':g-1,'rank':rank,'omitted':omitted,'cluster_counts':cluster_counts,'sample':work[['firm_id','year']].copy(),'firms':work.firm_id.nunique(),'cities':work.city_id.nunique() if 'city_id' in work else None,'outcome_sd':work[y].std(),'exposure_sd':work[x[0]].std()}


def contrast(model,weights):
    if any(k not in model['beta'] for k in weights):return {'b':np.nan,'se':np.nan,'p':np.nan,'ci_low':np.nan,'ci_high':np.nan,'not_identified':True}
    names=list(weights);w=np.array(list(weights.values()));b=float(model['beta'][names]@w);var=float(w@model['cov'].loc[names,names].to_numpy()@w)
    se=np.sqrt(max(0,var));df=model['df_resid_cluster'];crit=t.ppf(.975,df);p=2*t.sf(abs(b/se),df) if se else np.nan
    return {'b':b,'se':float(se),'p':float(p),'ci_low':float(b-crit*se),'ci_high':float(b+crit*se),'not_identified':False}
