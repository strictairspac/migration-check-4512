from sqlalchemy import Column,Integer,String,JSON,DateTime,ForeignKey,UniqueConstraint,func
from src.config.database import Base
class LineageMeta(Base):
 __tablename__='lineage_meta'
 id=Column(Integer,primary_key=True)
 version=Column(Integer,nullable=False,default=0)
 updated_at=Column(DateTime,server_default=func.now(),onupdate=func.now())
class LineageRegistration(Base):
 __tablename__='lineage_registrations'
 id=Column(Integer,primary_key=True)
 request_id=Column(String(160),unique=True,nullable=False)
 actor=Column(String(120),nullable=False)
 payload=Column(JSON,nullable=False)
 payload_digest=Column(String(64),nullable=False,default='')
 status=Column(String(20),nullable=False,default='accepted')
 version=Column(Integer,nullable=True)
 response=Column(JSON,nullable=True)
 created_at=Column(DateTime,server_default=func.now())
class LineageEdge(Base):
 __tablename__='lineage_edges'
 __table_args__=(UniqueConstraint('child_code','parent_code'),)
 id=Column(Integer,primary_key=True)
 child_code=Column(String(160),nullable=False,index=True)
 parent_code=Column(String(160),nullable=False,index=True)
 relation=Column(String(10),nullable=False)
 version=Column(Integer,nullable=False,index=True)
 note=Column(String(500),nullable=False,default='')
 created_by=Column(String(120),nullable=False,default='')
 registration_id=Column(Integer,ForeignKey('lineage_registrations.id'),nullable=True)
 created_at=Column(DateTime,server_default=func.now())
