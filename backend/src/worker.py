import time,logging,redis
from pathlib import Path
from src.config.settings import REDIS_URL
from src.config.database import Session
from src.models.batch import Batch
from src.models.mapping import Mapping
from src.models.run import Run,TargetRow
from src.services.migration import migrate,make_backup,key_digest,Cancelled
from src.services.audit import log
from src.services import runs as runs_service
q=redis.Redis.from_url(REDIS_URL)
def progress(run_id,info):
 Path('/tmp/worker-heartbeat').touch()
 with Session() as s:
  r=s.get(Run,run_id)
  if r.cancel_requested or r.status=='cancelled':raise Cancelled()
  r.progress=info;s.commit()
while True:
 Path('/tmp/worker-heartbeat').touch()
 try:
  item=q.blpop('migration-runs',timeout=2)
  if not item:continue
  run_id=int(item[1])
  with Session() as s:
   r=s.query(Run).filter_by(id=run_id).with_for_update().first()
   if not r or r.status!='queued':continue
   r.status='running';snapshot=r.snapshot;s.commit()
  try:
   result=migrate(snapshot['batch']['rows'],snapshot['mapping']['rules'],snapshot['mapping']['chunk_size'],lambda info:progress(run_id,info))
   result['backup']=make_backup(result,run_id,snapshot['batch']['name'])
   def check(r):
    if r.cancel_requested:raise Cancelled()
   runs_service.finalize(run_id,result,check)
   log('worker','run.completed',str(run_id))
  except Cancelled:
   with Session() as s:r=s.get(Run,run_id);r.status='cancelled';r.error='用户取消，未提交目标行';s.commit()
   log('worker','run.cancelled',str(run_id))
  except Exception as exc:
   logging.exception('migration failed')
   with Session() as s:r=s.get(Run,run_id);r.status='failed';r.error=str(exc)[:1000];s.commit()
 except Exception:logging.exception('worker loop');time.sleep(2)
