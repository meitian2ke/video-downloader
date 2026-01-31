"""
腾讯云 COS 上传模块
"""
import os
import logging
from qcloud_cos import CosConfig, CosS3Client

logger = logging.getLogger(__name__)

# COS 配置（从环境变量读取）
COS_SECRET_ID = os.getenv('COS_SECRET_ID', '')
COS_SECRET_KEY = os.getenv('COS_SECRET_KEY', '')
COS_BUCKET = os.getenv('COS_BUCKET', '')
COS_REGION = os.getenv('COS_REGION', 'ap-beijing')


def get_cos_client():
    """获取 COS 客户端"""
    if not all([COS_SECRET_ID, COS_SECRET_KEY, COS_BUCKET]):
        return None

    config = CosConfig(
        Region=COS_REGION,
        SecretId=COS_SECRET_ID,
        SecretKey=COS_SECRET_KEY,
    )
    return CosS3Client(config)


def upload_file(local_path: str, cos_key: str) -> dict:
    """上传单个文件到 COS"""
    client = get_cos_client()
    if not client:
        return {'success': False, 'error': 'COS 未配置'}

    try:
        response = client.upload_file(
            Bucket=COS_BUCKET,
            Key=cos_key,
            LocalFilePath=local_path,
        )
        url = f"https://{COS_BUCKET}.cos.{COS_REGION}.myqcloud.com/{cos_key}"
        logger.info(f"上传成功: {cos_key}")
        return {'success': True, 'url': url, 'etag': response.get('ETag')}
    except Exception as e:
        logger.error(f"上传失败: {e}")
        return {'success': False, 'error': str(e)}


def upload_video_folder(video_dir: str, uploader: str, title: str) -> dict:
    """上传整个视频文件夹到 COS"""
    client = get_cos_client()
    if not client:
        return {'success': False, 'error': 'COS 未配置'}

    results = []
    base_cos_path = f"{uploader}/{title}"

    for root, dirs, files in os.walk(video_dir):
        for filename in files:
            local_path = os.path.join(root, filename)
            # 计算相对路径
            rel_path = os.path.relpath(local_path, video_dir)
            cos_key = f"{base_cos_path}/{rel_path}"

            result = upload_file(local_path, cos_key)
            results.append({
                'file': rel_path,
                **result
            })

    success_count = sum(1 for r in results if r.get('success'))
    return {
        'success': success_count == len(results),
        'total': len(results),
        'uploaded': success_count,
        'files': results
    }
