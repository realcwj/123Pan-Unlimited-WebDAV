import time
import requests
from tqdm import tqdm
import base64
import json
import random

from utils import anonymizeId, makeAbsPath

from getGlobalLogger import logger

class Pan123:
    # Refer: https://github.com/AlistGo/alist/blob/main/drivers/123/util.go
    
    def __init__(self, sleepTime=0.1):
        # 等待时间 (基于输入值[60%, 140%]范围随机取样)
        self.sleepTime = lambda: random.uniform(sleepTime*0.6, sleepTime*1.4)
        # 初始化accessToken和headers
        self.accessToken = None
        self.headers = {
            "origin":        "https://www.123pan.com",
            "referer":       "https://www.123pan.com/",
            "authorization": None, # Bearer {accessToken}
            "user-agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            "platform":      "web",
            "app-version":   "3",
        }
        # 用于记录self.listFiles访问过的文件夹：{文件夹Id: 文件夹名称}
        self.listFilesVisited = {}
        # 用于记录self.listShare访问过的文件夹：{文件夹Id: 文件夹名称}
        self.listShareVisited = {}
    
    def getActionUrl(self, actionName):
        # 执行各类操作的Url
        LoginApi = "https://login.123pan.com/api"
        MainApi = "https://www.123pan.com/b/api"
        apis = {
            "SignIn":           f"{LoginApi}/user/sign_in",
            "Logout":           f"{MainApi}/user/logout",
            "UserInfo":         f"{MainApi}/user/info",
            "FileList":         f"{MainApi}/file/list/new",
            "DownloadInfo":     f"{MainApi}/file/download_info",
            "Mkdir":            f"{MainApi}/file/upload_request",
            "Move":             f"{MainApi}/file/mod_pid",
            "Rename":           f"{MainApi}/file/rename",
            "Trash":            f"{MainApi}/file/trash",
            "UploadRequest":    f"{MainApi}/file/upload_request",
            "UploadComplete":   f"{MainApi}/file/upload_complete",
            "S3PreSignedUrls":  f"{MainApi}/file/s3_repare_upload_parts_batch",
            "S3Auth":           f"{MainApi}/file/s3_upload_object/auth",
            "UploadCompleteV2": f"{MainApi}/file/upload_complete/v2",
            "S3Complete":       f"{MainApi}/file/s3_complete_multipart_upload",
            "ShareList":        f"{MainApi}/share/get",
            "TrashDelete":      f"{MainApi}/file/delete",
        }
        # 返回对应操作的API地址, 如果不存在则返回None
        return apis.get(actionName, None)

    def doLogin(self, username, password):
        # 登录操作
        # 如果包含'@'且'@'后面有'.'，则认为是邮箱格式
        if ("@" in username) and ("." in username.split("@")[-1]):
            # 邮箱登录
            payload = {
                "mail": username,
                "password": password,
                "type": 2,
            }
        else:
            # 用户名密码登录
            payload = {
                "passport": username,
                "password": password,
                "remember": True,
            }
        # 发送登录请求
        headers = {
			"origin": "https://www.123pan.com",
			"referer": "https://www.123pan.com/",
			"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
			"platform": "web",
			"app-version": "3",
		}
        try:
            response_data = requests.post(
                url = self.getActionUrl("SignIn"),
                headers = headers,
                json = payload
            ).json()
            # sendRequest方法会处理检查API响应中的'code'字段（登录成功时期望值为200）
            # 如果登录成功，'code'将是200
            token = response_data.get("data", {}).get("token") # 从响应数据中提取token
            if token:
                self.accessToken = token # 存储获取到的access_token
                self.headers["authorization"] = f"Bearer {self.accessToken}"
                logger.debug(f"登录成功，access_token: {self.accessToken[:10]}...") # 不记录完整token, 保护隐私
                return True
            else:
                # 理论上，如果code不是200或者token缺失，sendRequest的code检查应该已经捕获了此情况
                # 此处作为一个额外保障
                logger.error(f"登录失败: {json.dumps(response_data, ensure_ascii=False)}")
                return None
        except Exception as e:
            logger.error(f"登录请求发生异常: {e}", exc_info=True)
            self.accessToken = None
            return None
    
    def setAccessToken(self, token):
        self.accessToken = token
        self.headers["authorization"] = f"Bearer {self.accessToken}"
    
    def getAccessToken(self):
        return self.accessToken
    
    def doLogout(self):
        # 注销操作
        # 发送注销请求
        try:
            response_data = requests.post(
                url = self.getActionUrl("Logout"),
                headers = self.headers
            ).json()
            # sendRequest方法会处理检查API响应中的'code'字段（注销成功时期望值为200）
            if response_data.get("code") == 200:
                self.accessToken = None
                self.headers["authorization"] = None
                logger.debug("注销成功")
                return True
            else:
                logger.error(f"注销失败: {json.dumps(response_data, ensure_ascii=False)}")
                return None
        except Exception as e:
            logger.error(f"注销请求发生异常: {e}", exc_info=True)
            self.accessToken = None
            return None
        
    def listFiles(self, parentFileId):
        
        # 如果已经访问过这个文件夹，就跳过
        if parentFileId in self.listFilesVisited:
            return None
        
        yield {"isFinish": None, "message": f"获取文件列表中：parentFileId: {parentFileId}"}

        page = 0
        body = {
			"driveId":              "0",
			"limit":                "100",
			"next":                 "0",
			"orderBy":              "file_id",
			"orderDirection":       "desc",
			"parentFileId":         parentFileId,
			"trashed":              "false",
			"SearchData":           "",
			"Page":                 None,
			"OnlyLookAbnormalFile": "0",
			"event":                "homeListFile",
			"operateType":          "4",
			"inDirectSpace":        "false",
		}
        
        # 记录当前文件夹内的所有文件和文件夹
        ALL_ITEMS = []
        
        try:
            while True:
                # 更新Page参数
                page += 1
                body.update({"Page": f"{page}"})
                logger.debug(f"listFiles: 正在获取第 {page} 页, parentFileId: {parentFileId}")
                # 发送请求
                time.sleep(self.sleepTime())
                response_data = requests.get(
                    url = self.getActionUrl("FileList"),
                    headers = self.headers,
                    params = body
                ).json()
                if response_data.get("code") == 0:
                    response_data = response_data.get("data")
                    # 把文件列表添加到ALL_FILES
                    ALL_ITEMS.extend(response_data.get("InfoList"))
                    # 如果没有下一页，就退出循环
                    if (response_data.get("Next") == "-1") or (len(response_data.get("InfoList")) == 0):
                        logger.debug(f"listFiles: 已是最后一页 (parentFileId: {parentFileId}, page: {page})")
                        break
                    # 否则进入下一页 (等待 self.sleepTime 秒, 防止被封)
                    else:
                        logger.debug(f"listFiles: 等待 {self.sleepTime()} 秒后进入下一页 (parentFileId: {parentFileId}, page: {page})")
                        time.sleep(self.sleepTime())
                else:
                    logger.warning(f"获取文件列表失败 (parentFileId: {parentFileId}, page: {page}): {json.dumps(response_data, ensure_ascii=False)}")
                    yield {"isFinish": False, "message": f"获取文件列表失败：{response_data}"}

            # 递归获取子文件夹下的文件
            for sub_file in ALL_ITEMS:
                if sub_file.get("Type") == 1:
                    yield from self.listFiles(sub_file.get("FileId"))

            # 记录当前文件夹内的所有文件
            self.listFilesVisited[parentFileId] = ALL_ITEMS

        except Exception as e:
            logger.error(f"listFiles 请求发生异常 (parentFileId: {parentFileId}): {e}", exc_info=True)
            yield {"isFinish": False, "message": f"获取文件列表请求发生异常: {e}"}

    def exportFiles(self, parentFileId):
        # 读取文件夹
        yield {"isFinish": None, "message": f"读取文件夹中..."}
        yield from self.listFiles(parentFileId=parentFileId)
        yield {"isFinish": None, "message": f"读取文件夹完成"}
        # 清洗数据
        yield {"isFinish": None, "message": f"数据清洗中..."}
        ALL_ITEMS = []
        for key, value in self.listFilesVisited.items():
            # 遍历所有文件夹和文件列表
            for item in value:
                # 遍历所有文件和文件夹
                ALL_ITEMS.append({
                    "FileId": item.get("FileId"),
                    "FileName": item.get("FileName"),
                    "Type": item.get("Type"),
                    "Size": item.get("Size"),
                    "Etag": item.get("Etag"),
                    "parentFileId": item.get("ParentFileId"),
                    "AbsPath": item.get("AbsPath").split(f"{parentFileId}/")[-1], # 以输入的parentFileId作为根目录
                })
        yield {"isFinish": None, "message": f"数据清洗完成"}
        # 数据匿名化
        yield {"isFinish": None, "message": f"数据匿名化中..."}
        ALL_ITEMS = anonymizeId(ALL_ITEMS)
        yield {"isFinish": None, "message": f"数据匿名化完成"}
        # 清空读取记录
        self.listFilesVisited = {}
        # 返回url_safe的base64数据(防止被简单的内容审查程序读取内容)
        yield {"isFinish": True, "message": base64.urlsafe_b64encode(json.dumps(ALL_ITEMS, ensure_ascii=False).encode("utf-8")).decode("utf-8")}


    def createFolder(self, parentFileId, folderName, raw_data=False):
        # 由于爬虫爬取到的数据可能会将分享名重命名为英文符号，触发创建文件夹失败，所以需要将文件夹名中的特殊字符替换回中文符号
        folderName = folderName.replace(":", "：").replace("/", "／").replace("\\", "＼").replace("*", "＊").replace("?", "？")
        body = {
            "driveId":      0,
            "etag":         "",
            "fileName":     folderName,
            "parentFileId": parentFileId,
            "size":         0,
            "type":         1,
            # "duplicate": 1,
            # "NotReuse": True,
            # "event": "newCreateFolder",
            # "operateType": 1,
            # "RequestSource": None,
        }
        try:
            response_data = requests.post(
                url = self.getActionUrl("Mkdir"),
                headers = self.headers,
                json = body
            ).json()
            if response_data.get("code") == 0:
                if raw_data:
                    return {"isFinish": True, "message": response_data.get("data")}
                fileId = response_data.get("data").get("Info").get("FileId")
                logger.debug(f"创建文件夹成功: {folderName}, fileId: {fileId}")
                # 返回文件夹Id
                return {"isFinish": True, "message": fileId}
            else:
                logger.error(f"创建文件夹失败 (parentFileId: {parentFileId}, folderName: {folderName}): {json.dumps(response_data, ensure_ascii=False)}")
                return {"isFinish": False, "message": f"创建文件夹失败：{response_data}"}
        except Exception as e:
            logger.error(f"创建文件夹请求发生异常 (parentFileId: {parentFileId}, folderName: {folderName}): {e}", exc_info=True)
            return {"isFinish": False, "message": f"创建文件夹请求发生异常: {e}"}
    
    def uploadFile(self, etag, fileName, parentFileId, size, raw_data=False):
        body = {
            "driveId": 0,
            "etag": etag,
            "fileName": fileName,
            "parentFileId": parentFileId,
            "size": size,
            "type": 0,
            # "RequestSource": None,
            "duplicate": 2, # 2->覆盖 1->重命名 0->默认
        }
        try:
            response_data = requests.post(
                url = self.getActionUrl("UploadRequest"),
                headers = self.headers,
                json = body
            ).json()
            if response_data.get("code") == 0:
                fileId = response_data.get("data").get("Info").get("FileId")
                logger.debug(f"上传文件成功: {fileName}, fileId: {fileId}, parentFileId: {parentFileId}")
                if raw_data:
                    return {"isFinish": True, "message": response_data.get("data")}
                else:
                    # 返回文件Id
                    return {"isFinish": True, "message": fileId}
            else:
                logger.error(f"上传文件失败 (parentFileId: {parentFileId}, fileName: {fileName}): {json.dumps(response_data, ensure_ascii=False)}")
                return {"isFinish": False, "message": f"上传文件失败：{response_data}"}
        except Exception as e:
            logger.error(f"上传文件请求发生异常 (parentFileId: {parentFileId}, fileName: {fileName}): {e}", exc_info=True)
            return {"isFinish": False, "message": f"上传文件请求发生异常: {e}"}
    
    def deleteFile(self, fileList, clearTrash=False):
        trash_body = {
            "driveId": 0,
            "event": "intoRecycle",
            "operatePlace": 1,
			"operation": True,
			"fileTrashInfoList": fileList, # List[dict, ...]
        }
        deleteIdList = []
        for file in fileList:
            deleteIdList.append({"fileId": file.get("FileId")})
        delete_body = {
            "fileIdList": deleteIdList,
            "event": "recycleDelete",
            "operatePlace": 1,
            "RequestSource": None
            }
        try:
            response_data = requests.post(
                url = self.getActionUrl("Trash"),
                headers = self.headers,
                json = trash_body
            ).json()
            if response_data.get("code") == 0:
                logger.debug(f"删除文件成功: {fileList}")
                if not clearTrash:
                    return {"isFinish": True, "message": "删除文件成功"}
                else:
                    # 彻底删除文件（删除回收站里的文件）
                    response_data = requests.post(
                        url = self.getActionUrl("TrashDelete"),
                        headers = self.headers,
                        json = delete_body
                    ).json()
                    if response_data.get("code") == 7301:
                        logger.debug(f"彻底删除文件成功: {fileList}")
                        return {"isFinish": True, "message": "彻底删除文件成功"}
                    else:
                        logger.error(f"彻底删除文件失败: {json.dumps(response_data, ensure_ascii=False)}")
                        return {"isFinish": False, "message": f"彻底删除文件失败：{response_data}"}
            else:
                logger.error(f"删除文件失败: {json.dumps(response_data, ensure_ascii=False)}")
                return {"isFinish": False, "message": f"删除文件失败：{response_data}"}
                
                
        except Exception as e:
            logger.error(f"删除文件请求发生异常: {e}", exc_info=True)
            return {"isFinish": False, "message": f"删除文件请求发生异常: {e}"}

    def downloadFile(self, etag, fileId, S3KeyFlag, type, fileName, size):
        body = {
        "driveId": 0,
        "etag": etag,
        "fileId": fileId,
        "s3keyFlag": S3KeyFlag,
        "type": type,
        "fileName": fileName,
        "size": size
        }
        try:
            response_data = requests.post(
                url = self.getActionUrl("DownloadInfo"),
                headers = self.headers,
                json = body
            ).json()
            if response_data.get("code") == 0:
                logger.debug(f"获取文件下载链接成功: {response_data}")
                return {"isFinish": True, "message": response_data.get("data").get("DownloadUrl")}
            else:
                logger.error(f"获取文件下载链接失败: {json.dumps(response_data, ensure_ascii=False)}")
                return {"isFinish": False, "message": f"获取文件下载链接失败：{response_data}"}
        except Exception as e:
            logger.error(f"获取文件下载链接请求发生异常: {e}", exc_info=True)
            return {"isFinish": False, "message": f"获取文件下载链接请求发生异常: {e}"}
        

    def importFiles(self, base64Data, rootFolderName, filterIds = []):
        # 读取数据
        yield {"isFinish": None, "message": "正在读取数据..."}
        try:
            files_list = json.loads(base64.urlsafe_b64decode(base64Data))

            # 如果选择部分文件导入
            if filterIds:
                # 获取所有筛选出来的文件
                filterIds = set(filterIds)
                # 获取所有文件的绝对路径，将父级文件夹全都添加到filterIDs中
                folder_ids = set()
                filtered_files = [item for item in files_list if item.get("FileId") in filterIds]
                for item in filtered_files:
                    current_folder_ids = [int(_id) for _id in item.get("AbsPath").split("/") if _id]
                    folder_ids.update(current_folder_ids)
                # 将所有文件夹ID添加到filterIDs中
                filterIds.update(folder_ids)
                # 得到最终的文件列表
                files_list = [item for item in files_list if item.get("FileId") in filterIds]
                logger.debug(f"importFiles: 筛选出 {len(filtered_files)} 个文件, 共 {len(files_list)} 个文件")

        except Exception as e:
            logger.error(f"importFiles: 读取 base64Data 失败: {e}", exc_info=True)
            yield {"isFinish": False, "message": f"读取数据失败, 报错：{e}"}
        yield {"isFinish": None, "message": "数据读取完成"}

        ID_MAP = {} # {原文件夹ID: 新文件夹ID}

        yield {"isFinish": None, "message": "正在清洗数据..."}
        # 遍历数据，分类文件夹和文件
        ALL_FOLDERS = []
        ALL_FILES = []
        for item in files_list:
            if item.get("Type") == 1:
                ALL_FOLDERS.append({
                    **item,
                    "folderDepth": item.get("AbsPath").count("/"),
                })
            elif item.get("Type") == 0:
                ALL_FILES.append({
                    **item,
                    "fileDepth": item.get("AbsPath").count("/"),
                })
            else:
                logger.error(f"importFiles: 未知文件类型: {json.dumps(item, ensure_ascii=False)}")
                raise ValueError(f"未知类型：{item}")

        ALL_FOLDERS.sort(key=lambda x: x.get("folderDepth")) # 按照深度从0(根目录)开始排序
        yield {"isFinish": None, "message": "数据清洗完成"}

        yield {"isFinish": None, "message": "正在重建目录结构..."}
        # 先在根目录创建文件夹
        rootFolderId = self.createFolder(
            parentFileId = 0,
            folderName = rootFolderName
        )
        if rootFolderId.get("isFinish"): # 如果创建成功
            rootFolderId = rootFolderId.get("message") # 获取文件夹ID
        else:
            logger.error(f"importFiles: 创建根目录失败: {json.dumps(rootFolderId, ensure_ascii=False)}")
            yield rootFolderId # 返回错误信息
        # 如果分享的内容包含目录 (root目录放在目录的检测中记录)
        tqdm_bar = tqdm(total=len(ALL_FOLDERS))
        for folder in ALL_FOLDERS:
            # 如果是根目录, 获取原根目录的parentFileId, 映射到rootFolderId
            if folder.get("folderDepth") == 0:
                ID_MAP[folder.get("parentFileId")] = rootFolderId
            # 创建新文件夹
            newFolderId = self.createFolder(
                parentFileId = ID_MAP.get(folder.get("parentFileId")), # 基于新的目录结构创建文件夹
                folderName = folder.get("FileName") 
            )
            if newFolderId.get("isFinish"): # 如果创建成功
                newFolderId = newFolderId.get("message") # 获取文件夹ID
            else:
                logger.error(f"importFiles: 创建子目录 {folder.get('FileName')} 失败: {json.dumps(newFolderId, ensure_ascii=False)}")
                yield newFolderId # 返回错误信息
            
            # 映射原文件夹ID到新文件夹ID
            ID_MAP[folder.get("FileId")] = newFolderId
            
            tqdm_bar.update(1)
            tqdm_dict = tqdm_bar.format_dict
            
            yield {
                "isFinish": None,
                "message":f"[{tqdm_dict['n']}/{tqdm_dict['total']}][速度: {tqdm_dict['rate']:.2f} 个/秒][预估剩余时间: {(tqdm_dict['total']-tqdm_dict['n'])/tqdm_dict['rate']:.2f} 秒] 正在创建文件夹: {folder.get('FileName')}"
            }

        tqdm_bar.close()

        yield {"isFinish": None, "message": "目录结构重建完成"}

        # 遍历数据, 上传文件
        yield {"isFinish": None, "message": "正在上传文件..."}
        tqdm_bar = tqdm(total=len(ALL_FILES))
        for item in ALL_FILES:
            if item.get("fileDepth") == 0:
                ID_MAP[item.get("parentFileId")] = rootFolderId
            newFileId = self.uploadFile(
                etag = item.get("Etag"),
                fileName = item.get("FileName"),
                parentFileId = ID_MAP.get(item.get("parentFileId")), # 基于新的目录结构上传文件
                size = item.get("Size")
            )

            if newFileId.get("isFinish"): # 如果上传成功
                newFileId = newFileId.get("message") # 获取文件ID (目前没用到)
            else:
                logger.error(f"importFiles: 上传文件 {item.get('FileName')} 失败: {json.dumps(newFileId, ensure_ascii=False)}")
                yield newFileId # 返回错误信息
            
            tqdm_bar.update(1)
            tqdm_dict = tqdm_bar.format_dict

            yield {
                "isFinish": None,
                "message": f"[{tqdm_dict['n']}/{tqdm_dict['total']}][速度: {tqdm_dict['rate']:.2f} 个/秒][预估剩余时间: {(tqdm_dict['total']-tqdm_dict['n'])/tqdm_dict['rate']:.2f} 秒] 正在上传文件: {item.get('FileName')}"
            }

        tqdm_bar.close()
        
        yield {"isFinish": None, "message": "文件上传完成"}

        yield {"isFinish": True, "message": f"导入完成, 保存到123网盘根目录中的: >>> {rootFolderName} <<< 文件夹"}
    
    def listShare(self, parentFileId, shareKey, sharePwd):
        
        # 如果已经访问过这个文件夹，就跳过
        if parentFileId in self.listShareVisited:
            return None
        
        yield {"isFinish": None, "message": f"获取文件列表中：parentFileId: {parentFileId}"}

        page = 0
        body = {
			"limit":          "100",
			"next":           "0",
			"orderBy":        "file_id",
			"orderDirection": "desc",
			"parentFileId":   parentFileId,
			"Page":           None,
			"shareKey":       shareKey,
			"SharePwd":       sharePwd,
		}
        
        # 记录当前文件夹内的所有文件和文件夹
        ALL_ITEMS = []
        
        try:
            while True:
                # 更新Page参数
                page += 1
                body.update({"Page": f"{page}"})
                logger.debug(f"listShare: 正在获取第 {page} 页, parentFileId: {parentFileId}, shareKey: {shareKey}")
                # 发送请求
                time.sleep(self.sleepTime())
                response_data = requests.get(
                    url = self.getActionUrl("ShareList"),
                    headers = self.headers,
                    params = body
                ).json()
                if response_data.get("code") == 0:
                    response_data = response_data.get("data")
                    # 把文件列表添加到ALL_FILES
                    ALL_ITEMS.extend(response_data.get("InfoList"))
                    # 如果没有下一页，就退出循环
                    if (response_data.get("Next") == "-1") or (len(response_data.get("InfoList")) == 0):
                        logger.debug(f"listShare: 已是最后一页 (parentFileId: {parentFileId}, page: {page}, shareKey: {shareKey})")
                        break
                    # 否则进入下一页 (等待 self.sleepTime 秒, 防止被封)
                    else:
                        logger.debug(f"listShare: 等待 {self.sleepTime()} 秒后进入下一页 (parentFileId: {parentFileId}, page: {page}, shareKey: {shareKey})")
                        time.sleep(self.sleepTime())
                else:
                    logger.warning(f"listShare 获取文件列表失败 (parentFileId: {parentFileId}, page: {page}, shareKey: {shareKey}): {json.dumps(response_data, ensure_ascii=False)}")
                    yield {"isFinish": False, "message": f"获取文件列表失败：{response_data}"}

            # 递归获取子文件夹下的文件
            for sub_file in ALL_ITEMS:
                if sub_file.get("Type") == 1:
                    yield from self.listShare(
                        parentFileId = sub_file.get("FileId"),
                        shareKey = shareKey,
                        sharePwd = sharePwd
                    )

            # 记录当前文件夹内的所有文件
            self.listShareVisited[parentFileId] = ALL_ITEMS

        except Exception as e:
            logger.error(f"listShare 请求发生异常 (parentFileId: {parentFileId}, shareKey: {shareKey}): {e}", exc_info=True)
            yield {"isFinish": False, "message": f"获取文件列表请求发生异常: {e}"}

    def exportShare(self, shareKey, sharePwd, parentFileId=0):
        
        # 读取文件夹
        yield {"isFinish": None, "message": f"获取文件列表中..."}
        yield from self.listShare(
            parentFileId=parentFileId,
            shareKey=shareKey,
            sharePwd=sharePwd
            )
        yield {"isFinish": None, "message": f"获取文件列表完成"}
        # 生成路径
        yield {"isFinish": None, "message": f"重建文件路径结构中..."}
        self.listShareVisited = makeAbsPath(
            fullDict=self.listShareVisited,
            parentFileId=parentFileId
        )
        yield {"isFinish": None, "message": f"重建文件路径结构完成"}
        
        # 清洗数据
        yield {"isFinish": None, "message": f"清洗数据中..."}
        ALL_ITEMS = []
        for key, value in self.listShareVisited.items():
            # 遍历所有文件夹和文件列表
            for item in value:
                # 遍历所有文件和文件夹
                ALL_ITEMS.append({
                    "FileId": item.get("FileId"),
                    "FileName": item.get("FileName"),
                    "Type": item.get("Type"),
                    "Size": item.get("Size"),
                    "Etag": item.get("Etag"),
                    "parentFileId": item.get("ParentFileId"),
                    "AbsPath": item.get("AbsPath").split(f"{parentFileId}/")[-1], # 以输入的parentFileId作为根目录
                })
        yield {"isFinish": None, "message": f"清洗数据完成"}
        # 数据匿名化
        yield {"isFinish": None, "message": f"数据匿名化中..."}
        ALL_ITEMS = anonymizeId(ALL_ITEMS)
        yield {"isFinish": None, "message": f"数据匿名化完成"}
        # 清空读取记录
        self.listShareVisited = {}
        # 返回url_safe的base64数据(防止被简单的内容审查程序读取内容)
        yield {"isFinish": True, "message": base64.urlsafe_b64encode(json.dumps(ALL_ITEMS, ensure_ascii=False).encode("utf-8")).decode("utf-8")}