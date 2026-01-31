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


def list_videos(prefix: str = '', marker: str = '', max_keys: int = 100) -> dict:
    """列出 COS 中的视频文件夹"""
    client = get_cos_client()
    if not client:
        return {'success': False, 'error': 'COS 未配置'}

    try:
        response = client.list_objects(
            Bucket=COS_BUCKET,
            Prefix=prefix,
            Delimiter='/',
            Marker=marker,
            MaxKeys=max_keys
        )

        # 获取文件夹（CommonPrefixes）
        folders = []
        for cp in response.get('CommonPrefixes', []):
            folder_path = cp.get('Prefix', '')
            if folder_path:
                folders.append({
                    'path': folder_path,
                    'name': folder_path.rstrip('/').split('/')[-1]
                })

        # 获取文件
        files = []
        for item in response.get('Contents', []):
            key = item.get('Key', '')
            if key and not key.endswith('/'):
                files.append({
                    'key': key,
                    'name': key.split('/')[-1],
                    'size': item.get('Size', 0),
                    'last_modified': item.get('LastModified', ''),
                    'url': f"https://{COS_BUCKET}.cos.{COS_REGION}.myqcloud.com/{key}"
                })

        return {
            'success': True,
            'folders': folders,
            'files': files,
            'is_truncated': response.get('IsTruncated') == 'true',
            'next_marker': response.get('NextMarker', '')
        }
    except Exception as e:
        logger.error(f"列出文件失败: {e}")
        return {'success': False, 'error': str(e)}


def delete_folder(prefix: str) -> dict:
    """删除 COS 中的文件夹及其所有内容"""
    client = get_cos_client()
    if not client:
        return {'success': False, 'error': 'COS 未配置'}

    try:
        # 列出所有要删除的对象
        objects_to_delete = []
        marker = ''

        while True:
            response = client.list_objects(
                Bucket=COS_BUCKET,
                Prefix=prefix,
                Marker=marker,
                MaxKeys=1000
            )

            for item in response.get('Contents', []):
                objects_to_delete.append({'Key': item['Key']})

            if response.get('IsTruncated') == 'true':
                marker = response.get('NextMarker', '')
            else:
                break

        if not objects_to_delete:
            return {'success': False, 'error': '文件夹为空或不存在'}

        # 批量删除
        delete_response = client.delete_objects(
            Bucket=COS_BUCKET,
            Delete={'Object': objects_to_delete, 'Quiet': 'true'}
        )

        return {
            'success': True,
            'deleted_count': len(objects_to_delete)
        }
    except Exception as e:
        logger.error(f"删除文件夹失败: {e}")
        return {'success': False, 'error': str(e)}


def delete_file(key: str) -> dict:
    """删除单个文件"""
    client = get_cos_client()
    if not client:
        return {'success': False, 'error': 'COS 未配置'}

    try:
        client.delete_object(Bucket=COS_BUCKET, Key=key)
        return {'success': True, 'deleted': key}
    except Exception as e:
        logger.error(f"删除文件失败: {e}")
        return {'success': False, 'error': str(e)}


def get_file_url(key: str, expires: int = 3600) -> dict:
    """获取文件的预签名 URL"""
    client = get_cos_client()
    if not client:
        return {'success': False, 'error': 'COS 未配置'}

    try:
        url = client.get_presigned_url(
            Method='GET',
            Bucket=COS_BUCKET,
            Key=key,
            Expired=expires
        )
        return {'success': True, 'url': url}
    except Exception as e:
        logger.error(f"获取URL失败: {e}")
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
