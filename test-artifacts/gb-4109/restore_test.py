import os,sys,threading,time
os.environ['DATABASE_URL']='sqlite:////tmp/lineage-restore.db'
os.environ['JWT_SECRET']='test';os.environ['SEED_DEMO']='false';os.environ['REDIS_URL']='redis://127.0.0.1:6399/0'
sys.path.insert(0,'/workspace/backend')
if os.path.exists('/tmp/lineage-restore.db'):os.remove('/tmp/lineage-restore.db')
from src.config.database import Base,engine,Session
import src.models.identity,src.models.batch,src.models.mapping,src.models.run,src.models.lineage
Base.metadata.create_all(engine)
from src.models.batch import Batch
from src.models.mapping import Mapping
from src.models.run import Run
from src.models.identity import User
from src.utils.security import hash_password
from src.services import lineage,runs as runs_service
from src.services.migration import migrate,make_backup
RULES=[{'source':a,'target':b,'type':c,'required':True} for a,b,c in [('委托号','sample_code','text'),('检测项','test_name','text'),('结果','result_value','decimal'),('单位','unit','text'),('时间','measured_at','datetime')]]
def row(code,i):return {'委托号':code,'检测项':f'T{i}','结果':'1.5','单位':'MPa','时间':'2026-11-17T09:00:00+08:00'}
with Session() as s:
 s.add(User(email='admin@x',role='admin',password=hash_password('pw123456')))
 b=Batch(name='b',source_file='f',description='',rows=[row('A',1),row('M1',1)])
 s.add(b);s.flush();s.add(Mapping(name='m',batch_id=b.id,rules=RULES,chunk_size=5,note=''));s.commit()
 m=s.query(Mapping).first();bid,mid,bname,rows=r.mapping_id if False else b.id,m.id,b.name,b.rows
 # legacy run BEFORE lineage registered, no snapshot (simulate old data): accepted rows w/o lineage
 bpy=__import__('src.models.batch',fromlist=['Batch'])
with Session() as s:
 b=s.get(Batch,bid);m=s.get(Mapping,mid)
 legacy=Run(name='legacy',batch_id=bid,mapping_id=mid,status='completed',snapshot={})
 res=migrate(b.rows,m.rules,m.chunk_size);res['backup']=make_backup(res,999,'legacy')
 legacy.result=res;legacy.status='completed';s.add(legacy);s.flush();lid=legacy.id
 from src.models.run import TargetRow
 from src.services.migration import key_digest
 for i,x in enumerate(res['accepted_rows']):s.add(TargetRow(run_id=lid,ordinal=i,key_digest=key_digest(x),payload=x))
 s.commit()
print('legacy trace A',lineage.trace('A')['matched'],'(expect 2: A + M1 as own origin? M1 has no parent so only A row)')
print('legacy trace M1',lineage.trace('M1')['matched'])
# Now register lineage and run a new run
lineage.register([{'sample_code':'A','parent_sample_code':'P','relation':'split'},{'sample_code':'M1','parent_sample_code':'A','relation':'mix'},{'sample_code':'M1','parent_sample_code':'B','relation':'mix'}],'u','req-restore-01','')
with Session() as s:
 b=s.get(Batch,bid);m=s.get(Mapping,mid)
 brow=list(b.rows);mrules=m.rules;mchunk=m.chunk_size
 newrun=Run(name='new',batch_id=bid,mapping_id=mid,status='running',snapshot={})
 s.add(newrun);s.commit();rid=newrun.id
res=migrate(brow,mrules,mchunk);res['backup']=make_backup(res,rid,'new')
snap=runs_service.finalize(rid,res)
print('new run lineage v',snap['version'])
print('trace P (new run only)',lineage.trace('P')['matched'],'(expect 2: A and M1 via A)')
# restore old backup for the new run keeps lineage
bk=res['backup']
proof=runs_service.restore(rid,type('D',(),{'backup':bk})())
print('restore proof',proof['verified'],proof['lineage_version'])
print('trace P after restore',lineage.trace('P')['matched'],'(expect 2 still)')
# register a NEW parent after restore: should NOT alter restored run attribution
lineage.register([{'sample_code':'Q','parent_sample_code':'P','relation':'split'}],'u','req-restore-02','')
print('trace P after late register (should stay 2 for restored run, legacy unaffected)',lineage.trace('P')['matched'])
# legacy run should be traceable by its own sample only
print('legacy trace A still',lineage.trace('A')['matched'])
print('RESTORE OK')
