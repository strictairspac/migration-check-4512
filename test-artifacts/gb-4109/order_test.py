# Verify a run's lineage snapshot uses exactly one version even if registration happens concurrently
import os,sys,threading,time
os.environ['DATABASE_URL']='sqlite:////tmp/lineage-order.db'
os.environ['JWT_SECRET']='test';os.environ['SEED_DEMO']='false';os.environ['REDIS_URL']='redis://127.0.0.1:6399/0'
sys.path.insert(0,'/workspace/backend')
if os.path.exists('/tmp/lineage-order.db'):os.remove('/tmp/lineage-order.db')
from src.config.database import Base,engine,Session
import src.models.identity,src.models.batch,src.models.mapping,src.models.run,src.models.lineage
Base.metadata.create_all(engine)
from src.models.batch import Batch
from src.models.mapping import Mapping
from src.models.run import Run
from src.services import lineage,runs as runs_service
from src.services.migration import migrate,make_backup
RULES=[{'source':a,'target':b,'type':c,'required':True} for a,b,c in [('委托号','sample_code','text'),('检测项','test_name','text'),('结果','result_value','decimal'),('单位','unit','text'),('时间','measured_at','datetime')]]
def row(code,i):return {'委托号':code,'检测项':f'T{i}','结果':'1.5','单位':'MPa','时间':'2026-11-17T09:00:00+08:00'}
with Session() as s:
 b=Batch(name='b',source_file='f',description='',rows=[row('A',1),row('M1',1)]);s.add(b);s.flush()
 s.add(Mapping(name='m',batch_id=b.id,rules=RULES,chunk_size=5,note=''));s.commit();bid=b.id;mid=s.query(Mapping).first().id
lineage.register([{'sample_code':'M1','parent_sample_code':'A','relation':'mix'}],'u','req-order-0001','')
lineage.register([{'sample_code':'A','parent_sample_code':'P','relation':'split'}],'u','req-order-0002','')
# lineage process keeps upgrading while we finalize a run
stop=False
def churn():
 i=0
 while not stop:
  i+=1
  try:lineage.register([{'sample_code':f'churn{i}','parent_sample_code':'A','relation':'mix'}],'bg',f'churn-{i:08d}','')
  except Exception:pass
th=threading.Thread(target=churn,daemon=True);th.start()
time.sleep(0.2)
with Session() as s:
 b=s.get(Batch,bid);m=s.get(Mapping,mid)
 brow=list(b.rows);mrules=m.rules;mchunk=m.chunk_size
 r=Run(name='r',batch_id=bid,mapping_id=mid,status='running',snapshot={});s.add(r);s.commit();rid=r.id
res=migrate(brow,mrules,mchunk);res['backup']=make_backup(res,rid,'r')
snap=runs_service.finalize(rid,res)
time.sleep(0.3);stop=True;th.join(timeout=2)
# every edge in the snapshot must be <= version, and all same version or prior; M1 path uses A
vers={e['version'] for e in snap['edges']}
print('snapshot v',snap['version'],'edge versions',vers)
assert all(v<=snap['version'] for v in vers)
assert snap['row_lineage'] and all(v['sample_code'] for v in snap['row_lineage'].values())
m1={val['sample_code']:val for val in snap['row_lineage'].values()}['M1']
a={val['sample_code']:val for val in snap['row_lineage'].values()}['A']
print('M1 relations',m1['relations'],'paths',m1['paths'])
assert m1['relations']=={'A':'mix'} and a['relations']=={'P':'split'}
assert m1['paths']==[['M1','A','P']]
# trace for A should include A rows and M1 rows and the churn mixes (since they parent A) -> at least 2
tr=lineage.trace('P');print('trace P matched',tr['matched'])
assert tr['matched']>=2
print('ORDER OK')
