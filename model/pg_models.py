import os
from peewee import *
from playhouse.postgres_ext import PostgresqlExtDatabase, TSVectorField
import datetime
# 判断是否启用 PostgreSQL 同步


# 延迟初始化 Postgres 数据库
DB_PG = PostgresqlDatabase(None)

def init_postgres():
    DB_PG.init(
        os.getenv('PG_DB_NAME'),
        host=os.getenv('PG_DB_HOST'),
        port=int(os.getenv('PG_DB_PORT', 5432)),
        user=os.getenv('PG_DB_USER'),
        password=os.getenv('PG_DB_PASSWORD')
    )


class PgBaseModel(Model):
    class Meta:
        database = DB_PG

class SoraContentPg(PgBaseModel):  
    id = IntegerField(primary_key=True)  # 显式指定主键，用于同步 kc_id
    source_id = CharField(max_length=100)
    file_type = CharField(max_length=1)  # 简化做法

    content = TextField()
    content_seg = TextField(null=True)
    # content_seg_tsv = TSVectorField(null=True)  # GENERATED COLUMN
    file_size = BigIntegerField(null=True)
    duration = IntegerField(null=True)
    tag = CharField(max_length=200, null=True)
    thumb_file_unique_id = CharField(max_length=100, null=True)
    thumb_hash = CharField(max_length=64, null=True)
    
    owner_user_id = BigIntegerField(null=True)
    source_channel_message_id = BigIntegerField(null=True)
    stage = CharField(max_length=20, null=True)  # 可加 enum CHECK 限制
    plan_update_timestamp = BigIntegerField(null=True)

    class Meta:
        table_name = 'sora_content'

class SoraMediaPg(PgBaseModel):
    id = BigAutoField()
    content_id = ForeignKeyField(SoraContentPg, backref='media', column_name='content_id', on_delete='CASCADE')
    source_bot_name = CharField()
    file_id = CharField(null=True)
    thumb_file_id = CharField(null=True)

    class Meta:
        table_name = 'sora_media'
        indexes = ((('content_id', 'source_bot_name'), True),)
   
class FileExtension(PgBaseModel):
    id = AutoField()
    file_type = CharField()  # 如需限制范围可加 constraints
    file_unique_id = CharField()
    file_id = CharField()
    bot = CharField()
    user_id = CharField(null=True)
    create_time = DateTimeField()

    class Meta:
        table_name = 'file_extension'
        indexes = (
            (('file_unique_id', 'bot'), True),  # UNIQUE 约束
        )