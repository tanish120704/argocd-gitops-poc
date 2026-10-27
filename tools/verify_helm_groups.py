#!/usr/bin/env python3
"""Verify independently rendered service Apps preserve values and isolation."""
import argparse,subprocess,tempfile
from pathlib import Path
import yaml
p=argparse.ArgumentParser(); p.add_argument('--charts',required=True); p.add_argument('--helm',default='helm'); args=p.parse_args()
charts=Path(args.charts).resolve(); root=Path(__file__).resolve().parents[1]
groups=['foundation','core-platform','product-services','to-revisit']
def render(path,tenant,extra=(),values_file=None):
 command=[args.helm,'template',tenant,str(path)]
 if values_file: command+=['-f',str(values_file)]
 else: command+=['-f',str(charts/'values.yaml'),'-f',str(root/f'tenants/{tenant}/values.yaml')]
 result=subprocess.run(command+list(extra),check=True,capture_output=True,text=True)
 return [d for d in yaml.safe_load_all(result.stdout) if d]
def indexed(docs):
 result={}
 for d in docs:
  key=(d['kind'],d['metadata']['name']); assert key not in result,key; result[key]=d
 return result
members=[]
for group in groups:
 chart=yaml.safe_load((charts/'groups'/group/'Chart.yaml').read_text()); assert not chart.get('dependencies'),group
 members+=yaml.safe_load((charts/'groups'/group/'values.yaml').read_text())['_services']
assert len(members)==len(set(members))==50
assert set(members)=={d['name'] for d in yaml.safe_load((charts/'Chart.yaml').read_text())['dependencies']}
for tenant in ['tenant-one','tenant-b']:
 baseline=indexed(render(charts,tenant)); resources=[]; apps=[]; groups_before={}
 with tempfile.TemporaryDirectory() as temporary:
  value_file=Path(temporary)/'values.yaml'
  for group in groups:
   docs=render(charts/'groups'/group,tenant); groups_before[group]=indexed(docs)
   group_apps=[d for d in docs if d['kind']=='Application']; apps+=group_apps
   configs=[d for d in docs if d['kind']=='ConfigMap']; assert len(configs)==(6 if group=='foundation' else 0)
   resources+=configs
   for app in group_apps:
    source=app['spec']['source']; assert source['path'].startswith('charts/')
    assert app['metadata']['namespace']=='argocd' and app['spec']['project']=='tenants'
    assert app['spec']['destination']['namespace']=='tenant-'+tenant
    assert app['metadata']['annotations']['argocd.argoproj.io/sync-wave']=='1'
    value_file.write_text(yaml.safe_dump(source['helm']['valuesObject']))
    resources+=render(charts/source['path'],tenant,values_file=value_file)
 assert len(apps)==50 and len(indexed(apps))==50
 assert len(resources)==56 and indexed(resources)==baseline,tenant
 print(tenant+': 50 independent service Applications + six Foundation ConfigMaps reproduce all 56 original resources exactly.')
 if tenant=='tenant-b':
  for group in groups:
   changed=indexed(render(charts/'groups'/group,tenant,['--set','service-b.settings.logLevel=error']))
   differences=[key for key in changed if changed[key]!=groups_before[group][key]]
   assert differences==([('Application','tenant-b-service-b')] if group=='foundation' else []),differences
  print('Service B override changes only Service B Application values; all other Apps and Foundation configuration remain identical.')

# A service chart revision can also be selected independently of group peers.
revision=subprocess.check_output(['git','-C',str(charts),'rev-parse','HEAD'],text=True).strip()
before=indexed(render(charts/'groups/foundation','tenant-b'))
after=indexed(render(charts/'groups/foundation','tenant-b',['--set',f'_serviceRevisions.service-b={revision}']))
assert [key for key in after if after[key]!=before[key]]==[('Application','tenant-b-service-b')]
assert after[('Application','tenant-b-service-b')]['spec']['source']['targetRevision']==revision
print('Service B chart revision can be pinned independently without changing any peer Application.')
