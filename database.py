from peewee import MySQLDatabase, OperationalError
from pymysql import err as pymysql_err
import os

# 检查是否在本地开发环境中运行
if not os.getenv('GITHUB_ACTIONS'):
    from dotenv import load_dotenv
    load_dotenv()


db_config = {
    'db_name': os.getenv('DB_NAME'),
    'db_user': os.getenv('DB_USER'),
    'db_password': os.getenv('DB_PASSWORD'),
    'db_host': os.getenv('DB_HOST'),
    'db_sslmode': os.getenv('DB_SSLMODE','require'),
    'db_port': int(os.getenv('DB_PORT',3306)),
}

# 数据库配置
db = MySQLDatabase(
    db_config['db_name'],
    user=db_config['db_user'],
    password=db_config['db_password'],
    host=db_config['db_host'],
    port=db_config['db_port'],
    charset='utf8mb4',
    autorollback=True
)

def ensure_connection():
    """
    检查数据库连接是否正常，如无效则自动重连。
    """
    try:
        if db.is_closed():
            db.connect()
        else:
            db.execute_sql('SELECT 1')
    except (pymysql_err.InterfaceError, OperationalError):
        try:
            db.close()
        except:
            pass
        db.connect()

def initialize_db():
    ensure_connection()
   
