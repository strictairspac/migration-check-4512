import os,sys,tempfile
os.environ['DATABASE_URL']='sqlite:////tmp/lineage-test.db'
os.environ['JWT_SECRET']='test'
os.environ['SEED_DEMO']='false'
os.environ['REDIS_URL']='redis://localhost:6379/0'
sys.path.insert(0,'/workspace/backend')
if os.path.exists('/tmp/lineage-test.db'):os.remove('/tmp/lineage-test.db')
from src.config.database import Base,engine
import src.models.identity,src.models.batch,src.models.mapping,src.models.run,src.models.lineage
Base.metadata.create_all(engine)
from src.services import lineage
print(lineage.register([{'sample_code':'A','parent_sample_code':'P','relation':'split'}],'u','req-00000001','n'))
print(lineage.register([{'sample_code':'A','parent_sample_code':'P','relation':'split'}],'u','req-00000001','n'))
print(lineage.list_edges())
try:lineage.register([{'sample_code':'P','parent_sample_code':'A','relation':'split'}],'u','req-00000002')
except Exception as e:print('cycle blocked:',getattr(e,'detail',e))
print(lineage.register([{'sample_code':'M','parent_sample_code':'A','relation':'mix'},{'sample_code':'M','parent_sample_code':'B','relation':'mix'}],'u','req-00000003'))
print('trace M',lineage.trace('M'))
