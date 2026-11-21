from sqlalchemy import inspect,text
from src.config.database import Base,engine
def ensure_schema():
 import src.models.identity,src.models.batch,src.models.mapping,src.models.run,src.models.lineage  # noqa: F401
 Base.metadata.create_all(engine)
 inspector=inspect(engine)
 if 'runs' in inspector.get_table_names():
  cols={c['name'] for c in inspector.get_columns('runs')}
  if 'lineage' not in cols:
   with engine.begin() as c:c.execute(text('ALTER TABLE runs ADD COLUMN lineage JSON'))
 if 'lineage_registrations' in inspector.get_table_names():
  cols={c['name'] for c in inspector.get_columns('lineage_registrations')}
  if 'payload_digest' not in cols:
   with engine.begin() as c:c.execute(text("ALTER TABLE lineage_registrations ADD COLUMN payload_digest VARCHAR(64) NOT NULL DEFAULT ''"))
