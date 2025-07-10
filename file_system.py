import json
import base64
import yaml
from typing import Dict, Optional, List, Tuple

from models import FileNode, TYPE_DIRECTORY
from Pan123Database import Pan123Database

# 读取配置文件
with open("settings.yaml", "r", encoding="utf-8") as f:
    settings_data = yaml.safe_load(f.read())

# --- 内存缓存数据结构 ---
# 结构1: (rootFolderName -> (shareCode, codeHash)) 用于快速通过名字查找
MEMORY_CACHE_BY_NAME: Dict[str, Tuple[str, str]] = {}
# 结构2: 按 codeHash 前两位分桶的缓存 (e.g., {'0a': ['电影A', '游戏B'], 'ff': ['资料C']})
MEMORY_CACHE_BY_BUCKET: Dict[str, List[str]] = {}
# 所有哈希桶的名称列表，即 '00', '01', ..., 'ff'
HASH_BUCKET_NAMES: List[str] = [f"{i:02x}" for i in range(256)]

def load_data_into_memory(db: Pan123Database):
    """
    在服务启动时，将所有公开分享数据从数据库加载到内存，并按哈希分桶。
    """
    print("开始从数据库加载所有公开分享数据到内存...")
    page = 1
    all_shares = []
    
    # 保持循环获取，确保拿到所有数据。limit=10000可以有效减少DB查询次数。
    while True:
        print(f"正在读取分享数据 (第{page}批)...")
        # 您在 Pan123Database.py 中为 listData 添加了 limit 参数
        shares_page, is_end_page = db.listData(visibleFlag=True, page=page, limit=16384)
        all_shares.extend(shares_page)
        if is_end_page:
            break
        page += 1
    
    print(f"从 listData 获取到 {len(all_shares)} 条分享记录，开始获取详细 shareCode 并构建缓存...")

    # 初始化所有哈希桶为空列表
    for bucket_name in HASH_BUCKET_NAMES:
        MEMORY_CACHE_BY_BUCKET[bucket_name] = []

    # 遍历所有分享，填充两个缓存结构
    for codeHash, rootFolderName, _ in all_shares:
        data = db.getDataByHash(codeHash)
        if data:
            _rootFolderName, shareCode, _visibleFlag = data[0]
            
            # 1. 填充按名字查找的缓存
            # 注意：如果 rootFolderName 重复，后来的会覆盖前者。
            MEMORY_CACHE_BY_NAME[rootFolderName] = (shareCode, codeHash)
            
            # 2. 按哈希前缀分桶
            # codeHash 已经是小写，取前两位作为桶的 key
            bucket_key = codeHash[:2]
            if bucket_key in MEMORY_CACHE_BY_BUCKET:
                MEMORY_CACHE_BY_BUCKET[bucket_key].append(rootFolderName)
            else:
                # 理论上不会发生，因为我们已经初始化了所有桶
                print(f"警告: 发现无效的哈希前缀 '{bucket_key}' (来自 codeHash: {codeHash})")

        else:
            print(f"无法获取 codeHash '{codeHash}' 的详细数据，跳过此条目。")
            
    # 对每个桶内的分享名进行排序，以便显示时有序
    for bucket_key in MEMORY_CACHE_BY_BUCKET:
        MEMORY_CACHE_BY_BUCKET[bucket_key].sort()

    print(f"内存缓存构建完成！共加载 {len(MEMORY_CACHE_BY_NAME)} 条分享数据，并分配到 {len(HASH_BUCKET_NAMES)} 个哈希桶中。")

class VirtualFileSystem:
    """
    虚拟文件系统类 (哈希分桶 + 内存缓存)。
    """
    def __init__(self, db_path: str):
        self.db = Pan123Database(dbpath=db_path)
        load_data_into_memory(self.db)
        self.root = FileNode(id=-1, parent_id=-2, name="ROOT", type=TYPE_DIRECTORY, size=0, etag="", abs_path_str="/")
        print(f"虚拟文件系统已初始化，数据从内存读取。")
        print(f"请通过WebDAV客户端挂载：\n\n")
        print(f"链接（本机访问）: http://127.0.0.1:{settings_data.get('WEBDAV_PORT')}/")
        print(f"链接（局域网访问）: http://本机的局域网IP地址:{settings_data.get('WEBDAV_PORT')}/")
        print(f"链接（公网访问）: http://本机的公网IP地址:{settings_data.get('WEBDAV_PORT')}/")
        print(f"WebDAV 用户名: {settings_data.get('WEBDAV_USERNAME')}")
        print(f"WebDAV 密码: {settings_data.get('WEBDAV_PASSWORD')}")
        

    def _build_tree_from_share_code(self, share_code: str) -> List[FileNode]:
        try:
            json_data = json.loads(base64.urlsafe_b64decode(share_code))
        except (json.JSONDecodeError, base64.binascii.Error) as e:
            print(f"解析 shareCode 失败: {e}")
            return []
        nodes: Dict[int, FileNode] = {}
        for item in json_data:
            node = FileNode(id=item['FileId'], parent_id=item['parentFileId'], name=item['FileName'], type=item['Type'], size=item['Size'], etag=item['Etag'], abs_path_str=item.get('AbsPath', ''))
            nodes[item['FileId']] = node
        top_level_nodes = []
        for node in nodes.values():
            parent_id = node.parent_id
            if parent_id in nodes:
                nodes[parent_id].children.append(node)
                node.parent = nodes[parent_id]
            else:
                top_level_nodes.append(node)
        return top_level_nodes

    def get_node_by_path(self, path: str) -> Optional[FileNode]:
        path = path.strip('/')
        parts = path.split('/') if path else []
        
        # 请求根目录 ("/") -> 显示 256 个哈希桶文件夹
        if not parts:
            self.root.children = []
            for i, bucket_name in enumerate(HASH_BUCKET_NAMES):
                bucket_node = FileNode(
                    id=200000 + i, # 给哈希桶文件夹一个唯一的ID
                    parent_id=self.root.id,
                    name=bucket_name,
                    type=TYPE_DIRECTORY,
                    size=0,
                    etag=f"bucket_{bucket_name}",
                    abs_path_str=bucket_name,
                    parent=self.root
                )
                self.root.children.append(bucket_node)
            return self.root

        # 请求哈希桶文件夹 (e.g., "/0a") -> 显示该桶内的分享文件夹
        bucket_name = parts[0]
        if len(parts) == 1 and bucket_name in HASH_BUCKET_NAMES:
            bucket_node = FileNode(
                id=200000 + HASH_BUCKET_NAMES.index(bucket_name),
                parent_id=self.root.id,
                name=bucket_name,
                type=TYPE_DIRECTORY,
                size=0,
                etag=f"bucket_{bucket_name}",
                abs_path_str=bucket_name,
                parent=self.root
            )
            
            # 从内存中获取该桶的分享名列表
            share_names_in_bucket = MEMORY_CACHE_BY_BUCKET.get(bucket_name, [])
            
            bucket_node.children = []
            for name in share_names_in_bucket:
                # 从内存缓存中获取 codeHash
                _, codeHash = MEMORY_CACHE_BY_NAME.get(name, (None, None))
                if codeHash:
                    share_folder_node = FileNode(
                        id=int(codeHash[:8], 16),
                        parent_id=bucket_node.id,
                        name=name,
                        type=TYPE_DIRECTORY,
                        size=0,
                        etag=codeHash,
                        abs_path_str=name,
                        parent=bucket_node
                    )
                    bucket_node.children.append(share_folder_node)
            
            return bucket_node
        
        # 请求深层路径 (e.g., "/0a/电影合集/...")
        if len(parts) < 2:
            return None # 路径不完整

        bucket_name = parts[0]
        root_folder_name = parts[1]

        # 验证第一级目录是否是合法的哈希桶
        if bucket_name not in HASH_BUCKET_NAMES:
            return None
        
        # 快速从内存中获取分享数据
        share_data = MEMORY_CACHE_BY_NAME.get(root_folder_name)
        if not share_data:
            print(f"内存缓存中未找到分享: '{root_folder_name}'")
            return None
        
        shareCode, codeHash = share_data
        
        # 验证该分享是否确实属于这个哈希桶，增加路径的健壮性
        if codeHash[:2] != bucket_name:
            print(f"路径不匹配: 分享 '{root_folder_name}' (hash: {codeHash}) 不属于哈希桶 '{bucket_name}'")
            return None
        
        # 解析分享内部的文件结构
        top_level_nodes = self._build_tree_from_share_code(shareCode)

        # 创建一个临时的“分享根”节点
        share_root_node = FileNode(
            id=int(codeHash[:8], 16),
            parent_id=200000 + HASH_BUCKET_NAMES.index(bucket_name), # 父ID指向哈希桶
            name=root_folder_name,
            type=TYPE_DIRECTORY,
            size=0,
            etag=codeHash,
            abs_path_str=root_folder_name,
            children=top_level_nodes
        )
        for node in top_level_nodes:
            node.parent = share_root_node

        # 如果只请求到分享根目录这一层
        if len(parts) == 2:
            return share_root_node
        
        # 如果请求的是分享内部的更深路径
        current_node = share_root_node
        for part in parts[2:]: # 从第三个部分开始匹配
            found_child = None
            for child in current_node.children:
                if child.name == part:
                    found_child = child
                    break
            
            if found_child:
                current_node = found_child
            else:
                return None
        
        return current_node

# 实例化
vfs = VirtualFileSystem(db_path=settings_data.get("DATABASE_PATH"))