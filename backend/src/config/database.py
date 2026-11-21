from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from src.config.settings import DATABASE_URL
_options={'pool_pre_ping':True}
if DATABASE_URL.startswith('sqlite'):_options['connect_args']={'check_same_thread':False}
engine=create_engine(DATABASE_URL,**_options)
Session=sessionmaker(bind=engine)
Base=declarative_base()
