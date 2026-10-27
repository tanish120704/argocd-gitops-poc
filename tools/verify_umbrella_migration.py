#!/usr/bin/env python3
"""Gate the POC migration on exact rendered resources and compare live snapshots.
Snapshots are kubectl JSON. Ignores only Kubernetes bookkeeping and Argo tracking /
last-applied annotations; sync-wave annotations, labels and all payload fields count.
"""
import argparse, copy, hashlib, json, subprocess
from pathlib import Path
import yaml
p=argparse.ArgumentParser()
p.add_argument('--charts', required=True)
p.add_argument('--helm', default='helm')
p.add_argument('--before', required=True, help='Legacy ConfigMap list JSON')
p.add_argument('--legacy-values', required=True, help='Original inline Helm values extracted as YAML')
p.add_argument('--after', help='Optional post-migration ConfigMap list JSON')
p.add_argument('--before-app')
p.add_argument('--after-apps')
p.add_argument('--before-namespace')
p.add_argument('--after-namespace')
p.add_argument('--report', required=True)
a=p.parse_args()
charts=Path(a.charts).resolve(); root=Path(__file__).resolve().parents[1]
release='umbrella-tenant'; namespace='tenant-umbrella-tenant'
groups=['foundation','core-platform','product-services','to-revisit']
tracking='argocd.argoproj.io/tracking-id'
ignored_annotations={tracking,'kubectl.kubernetes.io/last-applied-configuration'}
server_metadata={'uid','resourceVersion','generation','creationTimestamp','managedFields','selfLink'}
def canonical(doc):
 d=copy.deepcopy(doc); m=d['metadata']
 for key in server_metadata: m.pop(key,None)
 m.setdefault('namespace',namespace)
 annotations=m.get('annotations',{})
 for key in ignored_annotations: annotations.pop(key,None)
 if not annotations: m.pop('annotations',None)
 return d

def indexed(documents):
 result={}
 for d in documents:
  if d['metadata']['name']=='kube-root-ca.crt': continue
  key=(d['apiVersion'],d['kind'],d['metadata'].get('namespace',namespace),d['metadata']['name'])
  assert key not in result, f'Duplicate ownership: {key}'
  result[key]=d
 return result

def render(path,values):
 result=subprocess.run([a.helm,'template',release,str(path),'--namespace',namespace,'-f',str(charts/'values.yaml'),'-f',str(values)],check=True,capture_output=True,text=True)
 return [d for d in yaml.safe_load_all(result.stdout) if d]

baseline=indexed(render(charts,Path(a.legacy_values)))
grouped={}; expected_owners={}
for group in groups:
 subprocess.run([a.helm,'dependency','build',str(charts/'groups'/group)],check=True,capture_output=True,text=True)
 resources=indexed(render(charts/'groups'/group,root/'legacy-tenants/umbrella-tenant/values.yaml'))
 assert not set(grouped)&set(resources), 'Overlapping group ownership'
 grouped.update(resources)
 expected_owners.update({key:release+'-'+group for key in resources})
assert len(baseline)==len(grouped)==56
assert {k:canonical(v) for k,v in baseline.items()}=={k:canonical(v) for k,v in grouped.items()}, 'STOP: target manifests differ from legacy render'
before=indexed(json.loads(Path(a.before).read_text())['items'])
assert set(before)==set(baseline), 'STOP: unexpected live resource inventory'
assert {k:canonical(v) for k,v in before.items()}=={k:canonical(v) for k,v in baseline.items()}, 'STOP: live resources differ from legacy render'
report={'tenant':release,'resources':56,'rendered_manifest_differences':0,'live_baseline_differences':0,'excluded_annotations':sorted(ignored_annotations),'groups':{g:sum(owner==release+'-'+g for owner in expected_owners.values()) for g in groups},'payload_sha256':{k[3]:hashlib.sha256(json.dumps(canonical(v),sort_keys=True).encode()).hexdigest() for k,v in before.items()}}
if a.after:
 after=indexed(json.loads(Path(a.after).read_text())['items'])
 assert set(after)==set(before), 'STOP: resources added or removed'
 assert all(after[k]['metadata']['uid']==before[k]['metadata']['uid'] for k in before), 'STOP: resource recreated'
 assert all(canonical(after[k])==canonical(before[k]) for k in before), 'STOP: tenant resource changed'
 assert all(after[k]['metadata']['annotations'][tracking].split(':')[0]==expected_owners[k] for k in before), 'STOP: incorrect group ownership'
 report.update({'live_after_differences':0,'resource_uid_changes':0,'tracking_owner_changes':sum(before[k]['metadata']['annotations'].get(tracking)!=after[k]['metadata']['annotations'].get(tracking) for k in before),'ownership_verified':True})
for before_path,after_path,label in [(a.before_namespace,a.after_namespace,'namespace'),(a.before_app,a.after_apps,'parent_application')]:
 assert bool(before_path)==bool(after_path), f'Provide both snapshots for {label}'
 if before_path:
  old=json.loads(Path(before_path).read_text()); new=json.loads(Path(after_path).read_text())
  if label=='parent_application':
   applications={d['metadata']['name']:d for d in new['items']}
   new=applications[release]
   expected_apps={release}|set(expected_owners.values())
   assert {name for name in applications if name==release or name.startswith(release+'-')}==expected_apps
   for name in expected_apps:
    app=applications[name]
    assert app['status']['sync']['status']=='Synced' and app['status']['health']['status']=='Healthy', name
    assert not app['status'].get('conditions'), f'{name}: Application conditions present'
    if name!=release: assert app['spec']['syncPolicy']['automated']['prune'], f'{name}: normal pruning not restored'
  assert old['metadata']['uid']==new['metadata']['uid'], f'STOP: {label} recreated'
  report[label+'_uid']=new['metadata']['uid']
  report[label+'_uid_changed']=False
Path(a.report).parent.mkdir(parents=True,exist_ok=True)
Path(a.report).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='payload_sha256'},indent=2))
