import json
import base64
import math
import yaml
from typing import Dict, Optional, List, Tuple

from models import FileNode, TYPE_DIRECTORY
from Pan123Database import Pan123Database

# 读取配置文件
with open("settings.yaml", "r", encoding="utf-8") as f:
    settings_data = yaml.safe_load(f.read())

MEMORY_CACHE_BY_NAME: Dict[str, Tuple[str, str]] = {}
MEMORY_CACHE_NAMES_LIST: List[str] = []
PAGE_SIZE = 100

def load_data_into_memory(db: Pan123Database):
    print("开始从数据库加载所有公开分享数据到内存...")
    page = 1
    all_shares = []
    
    while True:
        shares_page, is_end_page = db.listData(visibleFlag=True, page=page)
        all_shares.extend(shares_page)
        if is_end_page:
            break
        page += 1
    
    print(f"从 listData 获取到 {len(all_shares)} 条分享记录，开始获取详细 shareCode...")

    temp_name_list = []
    for codeHash, rootFolderName, _ in all_shares:
        data = db.getDataByHash(codeHash)
        if data:
            _rootFolderName, shareCode, _visibleFlag = data[0]
            MEMORY_CACHE_BY_NAME[rootFolderName] = (shareCode, codeHash)
            temp_name_list.append(rootFolderName)
        else:
            print(f"无法获取 codeHash '{codeHash}' 的详细数据，跳过此条目。")
            
    global MEMORY_CACHE_NAMES_LIST
    MEMORY_CACHE_NAMES_LIST = sorted(temp_name_list)

    print(f"内存缓存构建完成！共加载 {len(MEMORY_CACHE_BY_NAME)} 条分享数据。")

class VirtualFileSystem:
    """
    虚拟文件系统类（两级分页目录+内存缓存）。
    """
    def __init__(self, db_path: str):
        self.db = Pan123Database(dbpath=db_path)
        load_data_into_memory(self.db)
        self.root = FileNode(id=-1, parent_id=-2, name="ROOT", type=TYPE_DIRECTORY, size=0, etag="", abs_path_str="/")
        print(f"虚拟文件系统已初始化，数据从内存读取。")
        print(f"请通过WebDAV客户端挂载：")
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
        
        # 请求根目录 ("/") -> 显示分页文件夹
        if not parts:
            total_items = len(MEMORY_CACHE_NAMES_LIST)
            total_pages = math.ceil(total_items / PAGE_SIZE)

            self.root.children = []
            for i in range(1, total_pages + 1):
                page_folder_name = f"第{i}页"
                page_node = FileNode(
                    id=100000 + i,
                    parent_id=self.root.id,
                    name=page_folder_name,
                    type=TYPE_DIRECTORY,
                    size=0,
                    etag=f"page_{i}",
                    abs_path_str=page_folder_name, 
                    parent=self.root
                )
                self.root.children.append(page_node)
            return self.root

        # 请求分页文件夹 ("/第x页") -> 显示该页的分享文件夹
        if len(parts) == 1 and parts[0].startswith("第") and parts[0].endswith("页"):
            try:
                page_num_str = parts[0][1:-1]
                page_num = int(page_num_str)
            except ValueError:
                return None
            
            page_folder_name = parts[0]
            page_folder_node = FileNode(
                id=100000 + page_num,
                parent_id=self.root.id,
                name=page_folder_name,
                type=TYPE_DIRECTORY,
                size=0,
                etag=f"page_{page_num}",
                abs_path_str=page_folder_name,
                parent=self.root
            )
            
            start_index = (page_num - 1) * PAGE_SIZE
            end_index = start_index + PAGE_SIZE
            page_item_names = MEMORY_CACHE_NAMES_LIST[start_index:end_index]
            
            page_folder_node.children = []
            for name in page_item_names:
                _, codeHash = MEMORY_CACHE_BY_NAME.get(name, (None, None))
                if codeHash:
                    share_folder_node = FileNode(
                        id=int(codeHash[:8], 16),
                        parent_id=page_folder_node.id,
                        name=name,
                        type=TYPE_DIRECTORY,
                        size=0,
                        etag=codeHash,
                        abs_path_str=name,
                        parent=page_folder_node
                    )
                    page_folder_node.children.append(share_folder_node)
            
            return page_folder_node
        
        # 请求深层路径 (e.g., "/第1页/电影合集/...")
        if len(parts) < 2:
            return None

        root_folder_name = parts[1]
        
        share_data = MEMORY_CACHE_BY_NAME.get(root_folder_name)
        if not share_data:
            return None
        
        shareCode, codeHash = share_data
        
        top_level_nodes = self._build_tree_from_share_code(shareCode)

        # 创建一个临时的“分享根”节点
        share_root_node = FileNode(
            id=int(codeHash[:8], 16),
            parent_id=0,
            name=root_folder_name,
            type=TYPE_DIRECTORY,
            size=0, # size 是必需的
            etag=codeHash, # etag 是必需的
            abs_path_str=root_folder_name,
            children=top_level_nodes
        )
        for node in top_level_nodes:
            node.parent = share_root_node

        if len(parts) == 2:
            return share_root_node
        
        current_node = share_root_node
        for part in parts[2:]:
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


    
vfs = VirtualFileSystem(db_path=settings_data.get("DATABASE_PATH"))