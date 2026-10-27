#!/usr/bin/env python3
"""Group unmodified source charts into content-addressed GitOps artifacts."""
import argparse, copy, hashlib, json, shutil, subprocess, tempfile
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
REPO='git@github.com:tanish120704/argocd-gitops-poc.git'
def read(p): return yaml.safe_load(p.read_text())
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def files_hash(path):
 return {str(p.relative_to(path)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(path.rglob('*')) if p.is_file() and '.git' not in p.parts}
def merge(base,override):
 result=copy.deepcopy(base)
 for k,v in override.items(): result[k]=merge(result[k],v) if isinstance(v,dict) and isinstance(result.get(k),dict) else copy.deepcopy(v)
 return result
def main():
 p=argparse.ArgumentParser(); p.add_argument('--charts',required=True); p.add_argument('--helm',default='helm'); p.add_argument('--check',action='store_true'); a=p.parse_args()
 charts=Path(a.charts).resolve(); lock=json.loads((ROOT/'releases/charts.json').read_text())
 revision=subprocess.check_output(['git','-C',str(charts),'rev-parse','HEAD'],text=True).strip()
 if revision!=lock['revision']: raise SystemExit('Chart checkout does not match releases/charts.json')
 if subprocess.check_output(['git','-C',str(charts),'status','--porcelain'],text=True).strip(): raise SystemExit('Chart checkout must be clean')
 catalog=read(ROOT/'catalog/groups.yaml')['groups']; deps=read(charts/'Chart.yaml')['dependencies']; names=[d['name'] for d in deps]
 assigned=[n for g in catalog.values() for n in g['services']]
 assert sorted(assigned)==sorted(names) and len(set(assigned))==len(assigned),'Every service must belong to exactly one group'
 assigned_templates=[n for g in catalog.values() for n in g['umbrellaTemplates']]
 assert sorted(assigned_templates)==sorted(p.name for p in (charts/'templates').glob('*.yaml')),'Every root template must belong to exactly one group'
 assert [g['wave'] for g in catalog.values()]==[0,1,2,3]
 parent_values=read(charts/'values.yaml'); helm_version=subprocess.check_output([a.helm,'version','--short'],text=True).strip()
 tool_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(); changed=[]; rendered=0; reused=0
 def put(relative,content):
  path=ROOT/relative
  if not path.exists() or path.read_text()!=content:
   changed.append(str(relative))
   if not a.check: path.parent.mkdir(parents=True,exist_ok=True); path.write_text(content)
 def helm_render(chart,release,values,tmp):
  nonlocal rendered
  f=tmp/'input.yaml'; f.write_text(yaml.safe_dump(values,sort_keys=True))
  out=subprocess.check_output([a.helm,'template',release,str(chart),'-f',str(f)],text=True)
  rendered+=1; return [d for d in yaml.safe_load_all(out) if d]
 for tenant_file in sorted((ROOT/'tenants').glob('*/values.yaml')):
  tenant=tenant_file.parent.name; override=read(tenant_file); effective=merge(parent_values,override)
  state_path=ROOT/'generated/state'/f'{tenant}.json'; old=json.loads(state_path.read_text()) if state_path.exists() else {'components':{},'groups':{}}
  old_docs={}
  for group,info in old['groups'].items():
   artifact=ROOT/info['path']/'resources.yaml'
   if artifact.exists():
    for doc in yaml.safe_load_all(artifact.read_text()):
     if doc: old_docs[doc['metadata']['name']]=doc
  components={}; docs={}; fingerprints={}
  with tempfile.TemporaryDirectory() as temp:
   tmp=Path(temp)
   for name in names:
    values=merge(parent_values.get(name,{}),override.get(name,{})); values['global']=effective['global']
    fingerprint=digest({'files':files_hash(charts/'charts'/name),'values':values,'tool':tool_hash,'helm':helm_version})
    fingerprints[name]=fingerprint; resource=tenant+'-'+name
    if old['components'].get(name)==fingerprint and resource in old_docs:
     components[name]=[old_docs[resource]]; reused+=1
    else: components[name]=helm_render(charts/'charts'/name,tenant,values,tmp)
   root_chart=tmp/'umbrella'; root_chart.mkdir(); meta=read(charts/'Chart.yaml'); meta.pop('dependencies',None)
   (root_chart/'Chart.yaml').write_text(yaml.safe_dump(meta)); shutil.copytree(charts/'templates',root_chart/'templates'); (root_chart/'values.yaml').write_text(yaml.safe_dump({k:v for k,v in parent_values.items() if k not in names},sort_keys=True)); shutil.copy(charts/'values.schema.json',root_chart/'values.schema.json')
   root_values={k:v for k,v in effective.items() if k not in names}
   root_fingerprint=digest({'files':files_hash(root_chart),'values':root_values,'tool':tool_hash,'helm':helm_version}); fingerprints['_umbrella']=root_fingerprint
   old_root=[d for d in old_docs.values() if d.get('metadata',{}).get('labels',{}).get('poc.example.com/role')=='umbrella']
   if old['components'].get('_umbrella')==root_fingerprint and len(old_root)==len(assigned_templates):
    root_docs=old_root; reused+=1
   else: root_docs=helm_render(root_chart,tenant,root_values,tmp)
  for name,g in catalog.items():
   members=[d for service in g['services'] for d in components[service]]
   sections={'tenant-config.yaml':'platform'}
   sections.update({p:p[:-5] for p in g['umbrellaTemplates'] if p!='tenant-config.yaml'})
   wanted={sections[p] for p in g['umbrellaTemplates']}
   members += [d for d in root_docs if d['metadata']['labels']['poc.example.com/section'] in wanted]
   members.sort(key=lambda d:d['metadata']['name']); docs[name]=members
  assert sum(map(len,docs.values()))==56
  group_state={}
  for name,g in catalog.items():
   members=docs[name]; content='---\n'+yaml.safe_dump_all(members,sort_keys=False,explicit_start=False)
   artifact_hash=hashlib.sha256(content.encode()).hexdigest(); path=f'generated/artifacts/{tenant}/{name}/{artifact_hash}'
   put(Path(path)/'resources.yaml',content); group_state[name]={'path':path,'resourceCount':len(members),'sha256':artifact_hash}
   application={'apiVersion':'argoproj.io/v1alpha1','kind':'Application','metadata':{'name':f'{tenant}-{name}','namespace':'argocd','annotations':{'argocd.argoproj.io/sync-wave':str(g['wave'])},'labels':{'platform.example.com/tenant':tenant,'platform.example.com/group':name}},'spec':{'project':'tenants','source':{'repoURL':REPO,'targetRevision':'refs/heads/main','path':path,'directory':{'recurse':False}},'destination':{'server':'https://kubernetes.default.svc','namespace':f'tenant-{tenant}'},'syncPolicy':{'automated':{'prune':True,'selfHeal':True,'allowEmpty':False},'syncOptions':['CreateNamespace=true']}}}
   put(Path(f'generated/tenants/{tenant}/parent/{name}.yaml'),yaml.safe_dump(application,sort_keys=False))
  state={'chartsRevision':revision,'tenantValuesSha256':hashlib.sha256(tenant_file.read_bytes()).hexdigest(),'components':fingerprints,'groups':group_state}
  put(Path(f'generated/state/{tenant}.json'),json.dumps(state,indent=2,sort_keys=True)+'\n')
 print(f'Rendered {rendered} components; reused {reused}; '+str(len(changed))+' output files differ.')
 if a.check and changed: raise SystemExit('Stale generated output: '+', '.join(changed))
if __name__=='__main__': main()
