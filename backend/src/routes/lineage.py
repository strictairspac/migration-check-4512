from fastapi import APIRouter,Depends,Query
from src.middlewares.auth import current,writer
from src.schemas.business import LineageInput
from src.services import lineage
from src.services.audit import log
router=APIRouter()
@router.get('/lineage')
def listing(version:int|None=Query(default=None,ge=0),u=Depends(current)):return {'version':lineage.current_version_value(),'edges':lineage.list_edges(version)}
@router.post('/lineage/registrations')
def register(data:LineageInput,u=Depends(writer)):
 row=lineage.register([e.model_dump() for e in data.entries],u.email,data.request_id,data.note)
 log(u.email,'lineage.register',f"{row.get('request_id') or data.request_id} v{row['version']} {len(row['lines'])}条")
 return row
@router.get('/lineage/trace')
def trace(code:str=Query(min_length=1,max_length=160),u=Depends(current)):return lineage.trace(code)
