import os,sys,threading
os.environ['DATABASE_URL']='sqlite:////tmp/lineage-e2e.db'
os.environ['JWT_SECRET']='test';os.environ['SEED_DEMO']='false'
sys.path.insert(0,'/workspace/backend')
if os.path.exists('/tmp/lineage-e2e.db'):os.remove('/tmp/lineage-e2e.db')
from src.config.database import Base,engine,Session
import src.models.identity,src.models.batch,src.models.mapping,src.models.run,src.models.lineage
Base.metadata.create_all(engine)
from src.models.batch import Batch
from src.models.mapping import Mapping
from src.models.run import Run
from src.services import lineage, runs as runs_service
from src.services.migration import migrate,make_backup
RULES=[{'source':a,'target':b,'type':c,'required':True} for a,b,c in [('委托号','sample_code','text'),('检测项','test_name','text'),('结果','result_value','decimal'),('单位','unit','text'),('时间','measured_at','datetime')]]
# Seed batches with samples that are children of P1
def row(code,i):return {'委托号':code,'检测项':f'T{i}','结果':'420.5','单位':'MPa','时间':'2026-11-17T09:00:00+08:00'}
with Session() as s:
 b1=Batch(name='b1',source_file='f1.json',description='',rows=[row('A',1),row('A',2),row('M1',1),row('M1',2),row('Z',1)])
 s.add(b1);s.flush()
 s.add(Mapping(name='m1',batch_id=b1.id,rules=RULES,chunk_size=2,note=''));s.commit();bid=b1.id
# Lineage: A split from P1; M1 mix from A and B; Z unrelated
lineage.register([{'sample_code':'A','parent_sample_code':'P1','relation':'split'}],'u','req-lineage-01','')
lineage.register([{'sample_code':'M1','parent_sample_code':'A','relation':'mix'},{'sample_code':'M1','parent_sample_code':'B','relation':'mix'}],'u','req-lineage-02','')
# ensure synthetic roots B exist by registering B<-P2? B is root itself
def run_once(name,mapping_id):
 with Session() as s:
  m=s.get(Mapping,mapping_id);b=s.get(Batch,m.batch_id)
  r=Run(name=name,batch_id=b.id,mapping_id=m.id,status='running',snapshot={'batch':{'rows':b.rows,'name':b.name},'mapping':{'rules':m.rules,'chunk_size':m.chunk_size}})
  s.add(r);s.commit();rid=r.id
 res=migrate(b.rows if False else __import__('src.models.batch',fromlist=['Batch']).Batch.__table__ and eval('[]') ,RULES,2) if False else None
 return rid
with Session() as s:
 m=s.query(Mapping).first()
 r=Run(name='run-1',batch_id=m.batch_id,mapping_id=m.id,status='running',snapshot={})
 s.add(r);s.commit();rid=r.id
 b=s.get(Batch,m.batch_id);rules=m.rules;chunk=m.chunk_size;rows=b.rows;bname=b.name
result=migrate(rows,rules,chunk)
result['backup']=make_backup(result,rid,bname)
snap=runs_service.finalize(rid,result)
print('lineage version at commit:',snap['version'])
# Now trace P1 -> should find rows for A (2 rows) and M1 (2 rows, via A)
tr=lineage.trace('P1');print('trace P1 matched:',tr['matched'])
for rr in tr['runs']:
 for x in rr['rows']:print(' ',x['sample_code'],x['test_name'],x['provenance_paths'])
assert tr['matched']==4, tr
# Trace B (mix parent) should find M1's 2 rows only
trB=lineage.trace('B');print('trace B matched:',trB['matched'])
assert trB['matched']==2
# Trace Z unrelated single
trZ=lineage.trace('Z');print('trace Z matched:',trZ['matched']);assert trZ['matched']==1
# Add lineage AFTER commit -> frozen, should not change trace P1
lineage.register([{'sample_code':'Z','parent_sample_code':'P1','relation':'split'}],'u','req-lineage-03','')
tr2=lineage.trace('P1');print('after late lineage trace P1 matched:',tr2['matched']);assert tr2['matched']==4, 'frozen lineage broken'
# current lineage endpoint reflects new v
print('current version',lineage.current_version_value(),'edges',len(lineage.list_edges()))
# targets endpoint includes row lineage
tg=runs_service.targets(rid)
print('targets lineage source',tg['lineage_source'],'version',tg['lineage_version'])
assert all(x['lineage'] for x in tg['rows_with_lineage'])
print('E2E OK')
