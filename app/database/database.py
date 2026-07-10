from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config.config import DATABASE
import os

_db_dir = os.path.dirname(DATABASE)
if _db_dir:
    os.makedirs(_db_dir, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DATABASE}",
    connect_args={"check_same_thread": False},
    pool_pre_ping=True
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# ============================================================
# 自动迁移：为已有 SQLite 表添加缺失的列
# （SQLite 的 CREATE TABLE IF NOT EXISTS 不会自动为已有表新增列）
# ============================================================
def _auto_migrate():
    """自动检测并为模型中新增的列在 SQLite 表中添加对应字段"""
    try:
        from app.models.vital import Vital
        from app.models.alert import Alert
        from app.models.device import Device
        from app.models.patient import Patient
    except Exception:
        return

    insp = inspect(engine)
    _models = [Vital, Alert, Device, Patient]

    with engine.begin() as conn:
        for _model in _models:
            _tablename = _model.__tablename__
            if not insp.has_table(_tablename):
                continue
            existing_cols = {col["name"] for col in insp.get_columns(_tablename)}
            for col in _model.__table__.columns:
                colname = col.name
                if colname in existing_cols:
                    continue
                # 根据列类型推断 SQLite 类型
                coltype = col.type.compile(dialect=engine.dialect)
                default_clause = ""
                if not col.nullable and col.default is None and not col.primary_key:
                    default_clause = " DEFAULT ''" if "VARCHAR" in coltype.upper() or "TEXT" in coltype.upper() else " DEFAULT 0"
                try:
                    conn.execute(text(f"ALTER TABLE {_tablename} ADD COLUMN {colname} {coltype}{default_clause}"))
                    print(f"[DB] 已添加列: {_tablename}.{colname} ({coltype})")
                except Exception as e:
                    print(f"[DB] 添加列 {_tablename}.{colname} 时提示: {e}")

# 先创建表，再补列
Base.metadata.create_all(bind=engine)
_auto_migrate()

# DB依赖注入
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()