import threading
from datetime import datetime,timezone
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from src.config.database import Session,engine
from src.models.lineage import LineageMeta,LineageRegistration,LineageEdge
from src.services.migration import digest,key_digest
RELATIONS={'split':'分样','mix':'混样'}
MAX_ENTRIES=200
MAX_CODE=160
MAX_PATHS=50
MAX_TRACE_PATHS=20
MAX_STEPS=50000
_lock=threading.Lock()
def _now():return datetime.now(timezone.utc).isoformat()
def _clean(value,label):
 if not isinstance(value,str):raise HTTPException(422,label+'必须为字符串')
 value=value.strip()
 if not 1<=len(value)<=MAX_CODE:raise HTTPException(422,label+'长度须为1-160字符')
 return value
def normalize(entries,note=''):
 if not isinstance(entries,list) or not 1<=len(entries)<=MAX_ENTRIES:raise HTTPException(422,'每次登记须包含1-200条来路')
 if not isinstance(note,str) or len(note)>500:raise HTTPException(422,'备注最多500字符')
 seen={};out=[]
 for raw in entries:
  if not isinstance(raw,dict):raise HTTPException(422,'每条来路须为对象')
  child=_clean(raw.get('sample_code'),'子样编号')
  parent=_clean(raw.get('parent_sample_code'),'父样编号')
  relation=raw.get('relation')
  if relation not in RELATIONS:raise HTTPException(422,'关系必须为split（分样）或mix（混样）')
  pair=(child,parent)
  if pair in seen:
   if seen[pair]!=relation:raise HTTPException(422,'同一来路登记了互相矛盾的分样/混样关系')
   continue
  seen[pair]=relation;out.append({'sample_code':child,'parent_sample_code':parent,'relation':relation})
 out.sort(key=lambda x:(x['sample_code'],x['parent_sample_code'],x['relation']))
 return out,note
def _payload_digest(entries,note):return digest({'entries':entries,'note':note})
def _ensure_meta(s):
 if engine.dialect.name=='sqlite':s.execute(text('INSERT OR IGNORE INTO lineage_meta (id,version) VALUES (1,0)'))
 else:s.execute(text('INSERT INTO lineage_meta (id,version) VALUES (1,0) ON CONFLICT (id) DO NOTHING'))
 return s.query(LineageMeta).filter_by(id=1).with_for_update().one()
def current_version(s):
 row=s.query(LineageMeta).filter_by(id=1).first()
 return row.version if row else 0
def current_version_value():
 with Session() as s:return current_version(s)
def _edges(s,version=None):
 q=s.query(LineageEdge)
 if version is not None:q=q.filter(LineageEdge.version<=version)
 return q.order_by(LineageEdge.id).all()
def _parent_map(edges):
 parents={}
 for e in edges:parents.setdefault(e['child'],{})[e['parent']]=e['relation']
 return parents
def _reachable(parents,start,target):
 stack=[start];seen=set()
 while stack:
  node=stack.pop()
  if node==target:return True
  if node in seen:continue
  seen.add(node);stack.extend(parents.get(node,{}).keys())
 return False
def attribution(parents,code):
 ancestors=[];seen=set();stack=[code]
 while stack:
  node=stack.pop()
  for p in sorted(parents.get(node,{})):
   if p not in seen:seen.add(p);stack.append(p);ancestors.append(p)
 roots=[];pending=[code];visited=set()
 while pending:
  node=pending.pop()
  if node in visited:continue
  visited.add(node)
  ps=parents.get(node,{})
  if not ps:roots.append(node);continue
  pending.extend(sorted(ps))
 paths=[];stack=[(code,[code])];steps=0;truncated=False
 while stack:
  if len(paths)>=MAX_PATHS or steps>=MAX_STEPS:truncated=True;break
  node,path=stack.pop();steps+=1
  ps=sorted(parents.get(node,{}))
  if not ps:paths.append(path);continue
  for p in ps:
   if p in path:continue
   stack.append((p,path+[p]))
 paths.sort()
 return {'sample_code':code,'parents':sorted(parents.get(code,{})),'relations':parents.get(code,{}),'ancestors':sorted(ancestors),'roots':sorted(set(roots)),'paths':paths,'truncated':truncated}
def _relevant_edges(edges,codes):
 parents=_parent_map(edges);nodes=set()
 for code in codes:
  a=attribution(parents,code);nodes.add(code);nodes.update(a['ancestors'])
 return [e for e in edges if e['child'] in nodes]
def snapshot_for_run(s,rows):
 # Row lock on lineage_meta serializes version read against concurrent registration,
 # so a run's whole batch is attributed to exactly one lineage version.
 meta=_ensure_meta(s)
 codes=sorted({row['sample_code'] for row in rows})
 edges=_edges(s,meta.version)
 parents={}
 for e in edges:parents.setdefault(e.child_code,{})[e.parent_code]=e.relation
 cache={};row_lineage={}
 for row in rows:
  code=row['sample_code']
  if code not in cache:cache[code]=attribution(parents,code)
  row_lineage[key_digest(row)]=cache[code]
 snapshot_edges=[{'child':r.child_code,'parent':r.parent_code,'relation':r.relation,'version':r.version} for r in edges]
 return {'version':meta.version,'captured_at':_now(),'source':'registered','edges':_relevant_edges(snapshot_edges,codes),'row_lineage':row_lineage}
def _found(s,request_id):
 row=s.query(LineageRegistration).filter_by(request_id=request_id).first()
 if not row:return None
 response=row.response or {}
 if row.status=='rejected':return {'request_id':row.request_id,'replayed':True,'accepted':False,'version':None,'lines':[],'unchanged':False,'detail':response.get('detail','父样登记被拒绝'),'payload_digest':row.payload_digest}
 return {'request_id':row.request_id,'replayed':True,'accepted':True,'version':row.version,'lines':response.get('lines',[]),'unchanged':response.get('unchanged',False),'detail':'','payload_digest':row.payload_digest}
def _replay(found,expected):
 if found['payload_digest']!=expected:raise HTTPException(409,'同一回执编号提交了不同内容，请换一个回执编号')
 if not found['accepted']:raise HTTPException(409,found['detail'])
 return {k:v for k,v in found.items() if k!='payload_digest'}
def _plan(entries,active):
 for e in entries:
  if e['sample_code']==e['parent_sample_code']:return None,'自然键不可作为自身的父样：'+e['sample_code']
 by_child={}
 for e in entries:by_child.setdefault(e['sample_code'],[]).append(e)
 existing={}
 for e in active:existing.setdefault(e.child_code,{})[e.parent_code]=e.relation
 prospective={c:dict(v) for c,v in existing.items()}
 for child,items in by_child.items():
  relations={i['relation'] for i in items}
  old=existing.get(child,{})
  old_relations=set(old.values())
  if old_relations and old_relations!=relations:
   return None,'子样'+child+'已登记'+'/'.join(RELATIONS[r] for r in sorted(old_relations))+'来路，不能改登记为'+'/'.join(RELATIONS[r] for r in sorted(relations))+'；请核对原有谱系'
  if 'split' in relations:
   if len(items)>1:return None,'分样子样'+child+'只能登记一个父样来路'
   old_parent=next((p for p,r in old.items()),None)
   if old_parent and old_parent!=items[0]['parent_sample_code']:return None,'分样子样'+child+'已登记父样'+old_parent+'，与本次父样'+items[0]['parent_sample_code']+'冲突'
   prospective[child]={items[0]['parent_sample_code']:'split'}
  else:
   for i in items:prospective.setdefault(child,{})[i['parent_sample_code']]='mix'
 for e in entries:
  child,parent=e['sample_code'],e['parent_sample_code']
  if _reachable(prospective,parent,child):return None,'父样登记将形成环：'+child+' ← '+parent
 return prospective,None
def _reject(actor,request_id,entries,note,payload_digest,detail):
 with Session() as s:
  if s.query(LineageRegistration).filter_by(request_id=request_id).first():return
  s.add(LineageRegistration(request_id=request_id,actor=actor,payload={'entries':entries,'note':note},payload_digest=payload_digest,status='rejected',response={'detail':detail}))
  try:s.commit()
  except IntegrityError:s.rollback()
def register(entries,actor,request_id,note=''):
 entries,note=normalize(entries,note)
 request_id=(request_id or '').strip() if isinstance(request_id,str) else ''
 payload_digest=_payload_digest(entries,note)
 if not request_id:request_id='auto-'+payload_digest[:48]
 elif not 8<=len(request_id)<=160:raise HTTPException(422,'回执编号须为8-160字符，用于重试去重')
 with Session() as s:found=_found(s,request_id)
 if found:return _replay(found,payload_digest)
 with _lock:
  with Session() as s:
   meta=_ensure_meta(s)
   found=_found(s,request_id)
   if found:
    s.rollback();return _replay(found,payload_digest)
   active=s.query(LineageEdge).all()
   _,problem=_plan(entries,active)
   if problem:
    s.rollback();_reject(actor,request_id,entries,note,payload_digest,problem)
    raise HTTPException(409,problem)
   current={(e.child_code,e.parent_code):e for e in active}
   changed=[];created=False;new_version=meta.version
   reg=LineageRegistration(request_id=request_id,actor=actor,payload={'entries':entries,'note':note},payload_digest=payload_digest,status='accepted')
   try:
    s.add(reg);s.flush()
    for e in entries:
     child,parent,relation=e['sample_code'],e['parent_sample_code'],e['relation']
     existing=current.get((child,parent))
     if existing:
      if existing.note!=note:existing.note=note
      changed.append({'sample_code':child,'parent_sample_code':parent,'relation':relation,'relation_label':RELATIONS[relation],'status':'unchanged'})
      continue
     if not created:new_version=meta.version+1;created=True
     s.add(LineageEdge(child_code=child,parent_code=parent,relation=relation,version=new_version,note=note,created_by=actor,registration_id=reg.id))
     changed.append({'sample_code':child,'parent_sample_code':parent,'relation':relation,'relation_label':RELATIONS[relation],'status':'created'})
    if created:meta.version=new_version
    reg.version=new_version
    reg.response={'version':new_version,'lines':changed,'unchanged':not created}
    s.commit()
   except IntegrityError:
    s.rollback()
    with Session() as s2:found=_found(s2,request_id)
    if found:return _replay(found,payload_digest)
    raise HTTPException(409,'父样登记并发冲突，请重试')
   return {'request_id':request_id,'version':new_version,'replayed':False,'accepted':True,'unchanged':not created,'lines':changed}
def list_edges(version=None):
 with Session() as s:
  return [{'sample_code':r.child_code,'parent_sample_code':r.parent_code,'relation':r.relation,'relation_label':RELATIONS.get(r.relation,r.relation),'version':r.version,'note':r.note,'created_by':r.created_by,'created_at':r.created_at.isoformat() if r.created_at else None} for r in _edges(s,version)]
def paths_to(edges,sample,target,limit=MAX_TRACE_PATHS):
 parents={}
 for e in edges:parents.setdefault(e['child'],[]).append(e['parent'])
 out=[];steps=0;stack=[(sample,[sample])]
 while stack and len(out)<limit and steps<MAX_STEPS:
  node,path=stack.pop();steps+=1
  if node==target:out.append(path);continue
  for p in sorted(parents.get(node,[])):
   if p in path:continue
   stack.append((p,path+[p]))
 return out
def trace(code):
 code=_clean(code,'原样编号')
 from src.models.run import Run,TargetRow
 with Session() as s:
  runs={r.id:r for r in s.query(Run).filter_by(status='completed').all()}
  rows=s.query(TargetRow).order_by(TargetRow.run_id,TargetRow.ordinal).all()
  grouped={}
  for row in rows:
   run=runs.get(row.run_id)
   if not run:continue
   lin=run.lineage or {}
   attr=(lin.get('row_lineage') or {}).get(row.key_digest)
   sample=row.payload.get('sample_code')
   if attr:
    mode='registered';paths=[]
    if code==sample:matched=True;paths=[[code]]
    elif code in set(attr.get('ancestors') or []):matched=True;paths=[p for p in attr.get('paths') or [] if code in p]
    else:matched=False
    if matched and not paths:paths=paths_to(lin.get('edges') or [],attr.get('sample_code') or sample,code)
    roots=sorted({p[-1] for p in paths}) if paths else ([code] if matched else [])
   else:
    mode='legacy-original'
    matched=code==sample
    paths=[[code]] if matched else []
    roots=[code] if matched else []
   if not matched:continue
   grouped.setdefault(run.id,{'run_id':run.id,'run_name':run.name,'batch_id':run.batch_id,'lineage_version':lin.get('version',0),'lineage_source':lin.get('source','legacy'),'rows':[]})['rows'].append({'ordinal':row.ordinal,'key_digest':row.key_digest,'sample_code':sample,'test_name':row.payload.get('test_name'),'result_value':row.payload.get('result_value'),'attribution':mode,'provenance_paths':paths,'roots':roots})
 result=list(grouped.values())
 for bucket in result:bucket['count']=len(bucket['rows'])
 result.sort(key=lambda x:x['run_id'],reverse=True)
 return {'code':code,'matched':sum(x['count'] for x in result),'runs':result}
