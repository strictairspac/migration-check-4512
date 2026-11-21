import redis
from datetime import datetime,timezone
from fastapi import HTTPException
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models.batch import Batch
from src.models.mapping import Mapping
from src.models.run import Run,TargetRow
from src.utils.serialization import record
from src.services.migration import digest,key_digest,validate_backup
from src.services import lineage as lineage_service
queue=redis.Redis.from_url(REDIS_URL)
def finalize(run_id,result,progress_check=None):
 with Session() as s:
  r=s.query(Run).filter_by(id=run_id).with_for_update().first()
  if not r:raise HTTPException(404,'未找到对账运行')
  if progress_check:progress_check(r)
  snapshot=lineage_service.snapshot_for_run(s,result['accepted_rows'])
  for i,row in enumerate(result['accepted_rows']):s.add(TargetRow(run_id=run_id,ordinal=i,key_digest=key_digest(row),payload=row))
  r.result=result;r.lineage=snapshot;r.status='completed';s.commit()
  return snapshot
def list_items():
 with Session() as s:return [_summary(r) for r in s.query(Run).order_by(Run.id.desc()).limit(100).all()]
def _summary(r):
 item=record(r)
 lin=item.get('lineage') or {}
 item['lineage']={'version':lin.get('version',0),'source':lin.get('source','legacy'),'captured_at':lin.get('captured_at'),'row_count':len(lin.get('row_lineage') or {}),'edge_count':len(lin.get('edges') or [])} if item.get('lineage') is not None else None
 return item
def detail(item_id):
 with Session() as s:
  r=s.get(Run,item_id)
  if not r:raise HTTPException(404,'未找到对账运行')
  return record(r)
def create(data):
 with Session() as s:
  m=s.get(Mapping,data.mapping_id)
  if not m:raise HTTPException(404,'未找到字段映射')
  b=s.get(Batch,m.batch_id)
  r=Run(name=data.name,batch_id=b.id,mapping_id=m.id,status='queued',snapshot={'batch':record(b),'mapping':record(m)})
  s.add(r);s.commit();s.refresh(r);result=record(r)
 try:queue.rpush('migration-runs',result['id'])
 except redis.RedisError:
  with Session() as s:r=s.get(Run,result['id']);r.status='failed';r.error='队列不可用，请创建新任务';s.commit()
  raise HTTPException(503,'队列不可用，请稍后重试')
 return result
def cancel(item_id):
 with Session() as s:
  r=s.query(Run).filter_by(id=item_id).with_for_update().first()
  if not r:raise HTTPException(404,'未找到对账运行')
  if r.status not in ('queued','running'):raise HTTPException(409,'运行已终止，无法取消')
  r.cancel_requested=True
  if r.status=='queued':r.status='cancelled'
  s.commit();return record(r)
def targets(item_id):
 detail(item_id)
 with Session() as s:
  run=s.get(Run,item_id);lineage=run.lineage or {}
  rows=[{'ordinal':r.ordinal,'payload':r.payload,'lineage':(lineage.get('row_lineage') or {}).get(r.key_digest)} for r in s.query(TargetRow).filter_by(run_id=item_id).order_by(TargetRow.ordinal)]
 return {'rows':[x['payload'] for x in rows],'rows_with_lineage':rows,'count':len(rows),'checksum':digest([x['payload'] for x in rows]),'lineage_version':lineage.get('version',0),'lineage_source':lineage.get('source','legacy')}
def backup(item_id):
 r=detail(item_id)
 if r['status']!='completed':raise HTTPException(409,'仅完成运行可以备份')
 return r['result']['backup']
def restore(item_id,data):
 with Session() as s:
  r=s.query(Run).filter_by(id=item_id).with_for_update().first()
  if not r:raise HTTPException(404,'未找到对账运行')
  if r.status!='completed':raise HTTPException(409,'仅完成运行可以恢复')
  try:rows=validate_backup(data.backup,r.result['checksum'],item_id)
  except ValueError as e:raise HTTPException(422,str(e))
  before=s.query(TargetRow).filter_by(run_id=item_id).count()
  lineage=dict(r.lineage or {}) or None
  s.query(TargetRow).filter_by(run_id=item_id).delete()
  for i,row in enumerate(rows):s.add(TargetRow(run_id=item_id,ordinal=i,key_digest=key_digest(row),payload=row))
  s.flush()
  actual=[x.payload for x in s.query(TargetRow).filter_by(run_id=item_id).order_by(TargetRow.ordinal)]
  proof={'restored_at':datetime.now(timezone.utc).isoformat(),'previous_count':before,'restored_count':len(actual),'checksum':digest(actual),'verified':digest(actual)==r.result['checksum'],'lineage_version':(lineage or {}).get('version',0),'lineage_source':(lineage or {}).get('source','legacy'),'lineage_mode':'保留原认定谱系；当时未登记父样的行按原样追查'}
  if not proof['verified']:raise HTTPException(409,'恢复后校验失败，已回滚')
  r.recovery=(r.recovery or [])+[proof];s.commit();return proof
