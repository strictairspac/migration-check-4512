import os,sys,threading
os.environ['DATABASE_URL']='sqlite:////tmp/lineage-api.db'
os.environ['JWT_SECRET']='test';os.environ['SEED_DEMO']='false';os.environ['REDIS_URL']='redis://127.0.0.1:6399/0'
sys.path.insert(0,'/workspace/backend')
if os.path.exists('/tmp/lineage-api.db'):os.remove('/tmp/lineage-api.db')
from src.config.database import Base,engine,Session
import src.models.identity,src.models.batch,src.models.mapping,src.models.run,src.models.lineage
Base.metadata.create_all(engine)
from fastapi.testclient import TestClient
from src.main import app
from src.models.identity import User
from src.utils.security import hash_password
with Session() as s:
 s.add(User(email='op@x',role='operator',password=hash_password('pw123456')))
 s.add(User(email='vw@x',role='viewer',password=hash_password('pw123456')))
 s.commit()
c=TestClient(app)
with c:
 tok=c.post('/auth/login',json={'email':'op@x','password':'pw123456'}).json()['token']
 vt=c.post('/auth/login',json={'email':'vw@x','password':'pw123456'}).json()['token']
 H={'Authorization':'Bearer '+tok};V={'Authorization':'Bearer '+vt}
 def reg(entries,rid,note=''):
  return c.post('/lineage/registrations',headers=H,json={'request_id':rid,'entries':entries,'note':note})
 # 1. basic register + retry idempotency
 r1=reg([{'sample_code':'A','parent_sample_code':'P','relation':'split'}],'rec-00000001')
 print('first',r1.status_code,r1.json()['version'],r1.json()['replayed'])
 r2=reg([{'sample_code':'A','parent_sample_code':'P','relation':'split'}],'rec-00000001')
 print('retry',r2.status_code,r2.json()['version'],r2.json()['replayed'])
 assert r2.json()['replayed'] and r2.json()['version']==r1.json()['version']
 # retry same receipt different content -> 409
 r3=reg([{'sample_code':'A','parent_sample_code':'Q','relation':'split'}],'rec-00000001')
 print('conflicting retry',r3.status_code,r3.json()['detail'])
 assert r3.status_code==409
 # 2. cycle
 r4=reg([{'sample_code':'P','parent_sample_code':'A','relation':'split'}],'rec-00000002')
 print('cycle',r4.status_code,r4.json()['detail'])
 assert r4.status_code==409
 # replaying rejected receipt returns same 409, no new registration
 r5=reg([{'sample_code':'P','parent_sample_code':'A','relation':'split'}],'rec-00000002')
 print('replay rejected',r5.status_code,r5.json()['detail'])
 assert r5.status_code==409
 # 3. concurrent: X adds b->c, Y adds c->b, each plus unrelated branches
 #    start from scratch nodes b,c (roots). X: b<-c ; Y: c<-b
 results={}
 def go(name,entries,rid):
  results[name]=reg(entries,rid)
 t1=threading.Thread(target=go,args=('X',[{'sample_code':'B','parent_sample_code':'C','relation':'split'},{'sample_code':'U1','parent_sample_code':'U2','relation':'split'}],'rec-00000003'))
 t2=threading.Thread(target=go,args=('Y',[{'sample_code':'C','parent_sample_code':'B','relation':'split'},{'sample_code':'V1','parent_sample_code':'V2','relation':'split'}],'rec-00000004'))
 t1.start();t2.start();t1.join();t2.join()
 print('concurrent',{k:(v.status_code,v.json().get('version'),v.json().get('detail')) for k,v in results.items()})
 codes=sorted(v.status_code for v in results.values())
 assert codes==[200,409],codes
 edges={(e['sample_code'],e['parent_sample_code']) for e in c.get('/lineage',headers=H).json()['edges']}
 print('edges',edges)
 # the accepted order's unrelated branch must be present; rejected order's unrelated branch not required
 if results['X'].status_code==200:
  assert ('U1','U2') in edges and ('B','C') in edges and ('C','B') not in edges
 else:
  assert ('V1','V2') in edges and ('C','B') in edges and ('B','C') not in edges
 # 4. viewer can read but not register
 assert c.get('/lineage',headers=V).status_code==200
 rv=c.post('/lineage/registrations',headers=V,json={'request_id':'rec-00000009','entries':[{'sample_code':'x1x1','parent_sample_code':'y1y1','relation':'mix'}]})
 print('viewer register',rv.status_code);assert rv.status_code==403
 # 5. validation
 bad=reg([{'sample_code':'A'}],'rec-00000005');print('bad entry',bad.status_code)
 bad2=reg([{'sample_code':'A','parent_sample_code':'P','relation':'nope'}],'rec-00000006');print('bad relation',bad2.status_code)
 bad3=reg([{'sample_code':'A','parent_sample_code':'A','relation':'split'}],'rec-00000007');print('self',bad3.status_code,bad3.json()['detail'])
 # 6. mix multiple parents + trace unknown
 mix=reg([{'sample_code':'MX','parent_sample_code':'A','relation':'mix'},{'sample_code':'MX','parent_sample_code':'B','relation':'mix'}],'rec-00000008')
 print('mix',mix.status_code,mix.json()['version'],len(mix.json()['lines']))
 tr=c.get('/lineage/trace?code=NOPE',headers=V);print('trace none',tr.status_code,tr.json()['matched'])
 tr2=c.get('/lineage/trace?code=MX',headers=V);print('trace MX',tr2.status_code,tr2.json()['matched'])
 print('API OK')
