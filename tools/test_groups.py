#!/usr/bin/env python3
"""Prove service-level changes leave other tenant/group artifacts unchanged."""
import argparse, contextlib, importlib.util, io, json, shutil, sys, tempfile
from pathlib import Path
from unittest.mock import patch
import yaml
p=argparse.ArgumentParser(); p.add_argument('--charts',required=True); p.add_argument('--helm',default='helm'); args=p.parse_args()
repo=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('render_groups',repo/'tools/render_groups.py'); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp)
 for folder in ['catalog','releases','tenants','generated']: shutil.copytree(repo/folder,root/folder)
 module.ROOT=root
 def state(tenant): return json.loads((root/f'generated/state/{tenant}.json').read_text())
 one_before=state('tenant-one'); b_before=state('tenant-b')
 values=root/'tenants/tenant-b/values.yaml'; data=yaml.safe_load(values.read_text()); data['service-a']['settings']['logLevel']='error'; values.write_text(yaml.safe_dump(data,sort_keys=False))
 output=io.StringIO()
 with patch.object(sys,'argv',['render_groups.py','--charts',str(Path(args.charts).resolve()),'--helm',args.helm]),contextlib.redirect_stdout(output): module.main()
 assert 'Rendered 1 components; reused 101' in output.getvalue(),output.getvalue()
 assert state('tenant-one')==one_before
 b_after=state('tenant-b')
 for name in b_before['groups']:
  assert (b_before['groups'][name]==b_after['groups'][name])==(name!='foundation'),name
 # Service A currently belongs to Foundation, alongside the six root templates.
 old=list(yaml.safe_load_all((root/b_before['groups']['foundation']['path']/'resources.yaml').read_text()))
 new=list(yaml.safe_load_all((root/b_after['groups']['foundation']['path']/'resources.yaml').read_text()))
 changed=[a['metadata']['name'] for a,b in zip(old,new) if a!=b]
 assert changed==['tenant-b-service-a'],changed
 print('PASS: one Service A change rendered one component; only Tenant B Foundation changed; other groups and Tenant One are identical.')
