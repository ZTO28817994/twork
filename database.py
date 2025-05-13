from peewee import MySQLDatabase, OperationalError
import re
import os

# # 检查是否在本地开发环境中运行
# if not os.getenv('GITHUB_ACTIONS'):
#     from dotenv import load_dotenv
#     load_dotenv(dotenv_path='.29614663.env')
 
pattern = r"mysql://(.*?):(.*?)@(.*?):(\d+)/(.*)"
match = re.match(pattern, os.getenv('MYSQL_DSN',''))

if match:

    db_config = {
        'db_name': match.group(5),
        'db_user': match.group(1),
        'db_password':  match.group(2),
        'db_host': match.group(3),
        'db_sslmode': os.getenv('DB_SSLMODE','require'),
        'db_port': int(match.group(4)),
    }
else:
    db_config = {
        'db_name': os.getenv('MYSQL_DB_NAME'),
        'db_user': os.getenv('MYSQL_DB_USER'),
        'db_password': os.getenv('MYSQL_DB_PASSWORD'),
        'db_host': os.getenv('MYSQL_DB_HOST'),
        'db_sslmode': os.getenv('DB_SSLMODE','require'),
        'db_port': int(os.getenv('MYSQL_DB_PORT',3306)),
    }

# 数据库配置
db = MySQLDatabase(
    db_config['db_name'],
    user=db_config['db_user'],
    password=db_config['db_password'],
    host=db_config['db_host'],
    port=db_config['db_port'],
    charset='utf8mb4',
    autorollback=True,
    autoconnect=True
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
    except (OperationalError):
        try:
            db.close()
        except:
            pass
        db.connect()

def initialize_db():
    ensure_connection()
   
