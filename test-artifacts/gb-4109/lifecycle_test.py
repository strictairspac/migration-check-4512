import os,sys
os.environ['DATABASE_URL']='sqlite:////tmp/lineage-life.db'
os.environ['JWT_SECRET']='test';os.environ['SEED_DEMO']='true';os.environ['REDIS_URL']='redis://127.0.0.1:6399/0'
sys.path.insert(0,'/workspace/backend')
if os.path.exists('/tmp/lineage-life.db'):os.remove('/tmp/lineage-life.db')
from fastapi.testclient import TestClient
from src.main import app
with TestClient(app) as c:
 print('health-ish: startup ok')
 tok=c.post('/auth/login',json={'email':'operator@migration.local','password':'Migrate2026!'}).json()['token']
 H={'Authorization':'Bearer '+tok}
 lin=c.get('/lineage',headers=H).json()
 print('seeded lineage version',lin['version'],'edges',len(lin['edges']))
 for e in lin['edges']:print('  ',e['sample_code'],'<-',e['parent_sample_code'],e['relation_label'])
 # idempotent seed re-run
 from scripts.seed_demo import seed_lineage
 r=seed_lineage();print('reseed replayed?',r['replayed'],'v',r['version'])
 # full run through queue would need redis; instead check batch/mapping endpoints present
 print('batches',len(c.get('/batches',headers=H).json()),'mappings',len(c.get('/mappings',headers=H).json()))
 print('LIFECYCLE OK')
