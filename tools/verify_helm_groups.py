#!/usr/bin/env python3
"""Verify direct Helm grouping preserves data and isolates a Service B change."""
import argparse,subprocess
from pathlib import Path
import yaml
p=argparse.ArgumentParser(); p.add_argument('--charts',required=True); p.add_argument('--helm',default='helm'); args=p.parse_args()
charts=Path(args.charts).resolve(); root=Path(__file__).resolve().parents[1]
groups=['foundation','core-platform','product-services','to-revisit']
def render(path,tenant,extra=()):
 result=subprocess.run([args.helm,'template',tenant,str(path),'-f',str(charts/'values.yaml'),'-f',str(root/f'tenants/{tenant}/values.yaml'),*extra],check=True,capture_output=True,text=True)
 docs=[x for x in yaml.safe_load_all(result.stdout) if x]
 return {d['metadata']['name']:d for d in docs}
for group in groups:
 subprocess.run([args.helm,'dependency','build',str(charts/'groups'/group)],check=True,capture_output=True,text=True)
for tenant in ['tenant-one','tenant-b']:
 baseline=render(charts,tenant); grouped={}; results={}
 for group in groups:
  results[group]=render(charts/'groups'/group,tenant)
  assert not (set(grouped)&set(results[group])), 'Overlapping resource ownership'
  grouped.update(results[group])
 assert len(grouped)==56 and grouped==baseline, tenant
 print(tenant+': all four Helm groups exactly match the original 56-resource umbrella render.')
 if tenant=='tenant-b':
  for group in groups:
   modified=render(charts/'groups'/group,tenant,['--set','service-b.settings.logLevel=error'])
   assert (modified!=results[group])==(group=='foundation'),group
   changed=[name for name in modified if modified[name]!=results[group][name]]
   assert changed==(['tenant-b-service-b'] if group=='foundation' else []),changed
  print('Service B override changes only its ConfigMap in Foundation; other groups render identical manifests.')
