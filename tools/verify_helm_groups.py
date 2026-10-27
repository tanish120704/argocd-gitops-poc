#!/usr/bin/env python3
"""Verify direct Helm grouping preserves data and isolates a Service B change."""
import argparse,subprocess,copy
from pathlib import Path
import yaml
p=argparse.ArgumentParser(); p.add_argument('--charts',required=True); p.add_argument('--helm',default='helm'); args=p.parse_args()
charts=Path(args.charts).resolve(); root=Path(__file__).resolve().parents[1]
groups=['foundation','core-platform','product-services','to-revisit']
def render(path,tenant,extra=()):
 result=subprocess.run([args.helm,'template',tenant,str(path),'-f',str(charts/'values.yaml'),'-f',str(root/f'tenants/{tenant}/values.yaml'),*extra],check=True,capture_output=True,text=True)
 docs=[x for x in yaml.safe_load_all(result.stdout) if x]
 return {d['metadata']['name']:d for d in docs}
def without_waves(resources):
 result=copy.deepcopy(resources)
 for resource in result.values():
  metadata=resource['metadata']; annotations=metadata.get('annotations',{})
  annotations.pop('argocd.argoproj.io/sync-wave',None)
  if not annotations: metadata.pop('annotations',None)
 return result
for group in groups:
 subprocess.run([args.helm,'dependency','build',str(charts/'groups'/group)],check=True,capture_output=True,text=True)
for tenant in ['tenant-one','tenant-b']:
 baseline=render(charts,tenant); grouped={}; results={}
 for group in groups:
  results[group]=render(charts/'groups'/group,tenant)
  assert not (set(grouped)&set(results[group])), 'Overlapping resource ownership'
  grouped.update(results[group])
 assert len(grouped)==56 and without_waves(grouped)==without_waves(baseline), tenant
 foundation=results['foundation']
 service_names=[d['name'] for d in yaml.safe_load((charts/'groups/foundation/Chart.yaml').read_text())['dependencies']]
 for wave,service in enumerate(service_names):
  assert foundation[tenant+'-'+service]['metadata']['annotations']['argocd.argoproj.io/sync-wave']==str(wave)
 for resource in foundation.values():
  if resource['metadata']['labels']['poc.example.com/role']=='umbrella':
   assert resource['metadata']['annotations']['argocd.argoproj.io/sync-wave']=='-1'
 for name in groups[1:]:
  assert all('argocd.argoproj.io/sync-wave' not in d['metadata'].get('annotations',{}) for d in results[name].values())
 print(tenant+': all 56 resources retain their data; Foundation waves -1 through 11 verified; other groups unchanged.')
 if tenant=='tenant-b':
  for group in groups:
   modified=render(charts/'groups'/group,tenant,['--set','service-b.settings.logLevel=error'])
   assert (modified!=results[group])==(group=='foundation'),group
   changed=[name for name in modified if modified[name]!=results[group][name]]
   assert changed==(['tenant-b-service-b'] if group=='foundation' else []),changed
  print('Service B override changes only its ConfigMap in Foundation; other groups render identical manifests.')

base=render(charts/'groups/foundation','tenant-b')
overridden=render(charts/'groups/foundation','tenant-b',['--set','service-b.syncWave=8'])
assert [name for name in overridden if overridden[name]!=base[name]]==['tenant-b-service-b']
assert overridden['tenant-b-service-b']['metadata']['annotations']['argocd.argoproj.io/sync-wave']=='8'
assert without_waves(overridden)==without_waves(base)
for value in ['invalid', '-2']:
 result=subprocess.run([args.helm,'template','invalid',str(charts/'groups/foundation'),'-f',str(charts/'values.yaml'),'--set','service-b.syncWave='+value],capture_output=True,text=True)
 assert result.returncode and 'schema' in result.stderr.lower(), result.stderr
print('Tenant service-wave override affects metadata only; non-integer and negative service waves are rejected.')
