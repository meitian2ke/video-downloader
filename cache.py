"""
Redis 缓存模块 - COS 文件列表缓存
"""
import os
import json
import redis
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))
CACHE_TTL = int(os.getenv('CACHE_TTL', '300'))  # 5分钟过期

# Redis 连接池
_redis_pool = None


def get_redis() -> redis.Redis:
    """获取 Redis 连接"""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True
        )
    return redis.Redis(connection_pool=_redis_pool)


def get_cos_cache(prefix: str = '') -> Optional[dict]:
    """从缓存获取 COS 文件列表"""
    try:
        r = get_redis()
        key = f"cos:list:{prefix}"
        data = r.get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.error(f"读取缓存失败: {e}")
    return None


def set_cos_cache(prefix: str, data: dict, ttl: int = None):
    """设置 COS 文件列表缓存"""
    try:
        r = get_redis()
        key = f"cos:list:{prefix}"
        r.setex(key, ttl or CACHE_TTL, json.dumps(data, ensure_ascii=False))
    except Exception as e:
        logger.error(f"写入缓存失败: {e}")


def invalidate_cos_cache(prefix: str = ''):
    """使缓存失效（删除相关缓存）"""
    try:
        r = get_redis()
        # 删除该前缀及其父级的缓存
        keys_to_delete = [f"cos:list:{prefix}"]

        # 删除父级目录缓存
        parts = prefix.rstrip('/').split('/')
        for i in range(len(parts)):
            parent = '/'.join(parts[:i]) + '/' if i > 0 else ''
            keys_to_delete.append(f"cos:list:{parent}")

        # 删除根目录缓存
        keys_to_delete.append("cos:list:")

        for key in set(keys_to_delete):
            r.delete(key)

        logger.info(f"已清除缓存: {keys_to_delete}")
    except Exception as e:
        logger.error(f"清除缓存失败: {e}")


def invalidate_all_cos_cache():
    """清除所有 COS 缓存"""
    try:
        r = get_redis()
        keys = r.keys("cos:list:*")
        if keys:
            r.delete(*keys)
            logger.info(f"已清除所有 COS 缓存: {len(keys)} 个")
    except Exception as e:
        logger.error(f"清除所有缓存失败: {e}")
