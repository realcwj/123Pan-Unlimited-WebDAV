# [123云盘](https://www.123pan.com) 无限制挂载工具（配置参数介绍文档）

## 目录

- [123云盘 无限制挂载工具（配置参数介绍文档）](#123云盘-无限制挂载工具配置参数介绍文档)
  - [目录](#目录)
  - [配置参数](#配置参数)

## 配置参数

```yaml
# 文件夹结构示例：
# 123Pan-Unlimited-WebDAV/
# ├── main.exe
# ├── PAN123DATABASE.db
# └── settings.yaml


# 最新数据库下载地址: https://github.com/realcwj/123Pan-Unlimited-Share/releases/tag/database
# 注意: 
# - 更新数据库, 文件夹索引可能会改变
# - 你需要进入挂载WebDAV的播放器（比如，网易爆米花、VidHub、Infuse等），重新搜索资源、重新刮削


# 数据库路径（保持默认即可，如果报错再按照下面示例修改）
# Windows 填写示例(填写完整路径，从盘符开始): X:/.../PAN123DATABASE.db
# Linux 填写示例(填写完整路径，从/开始): /home/username/.../PAN123DATABASE.db
DATABASE_PATH: "./PAN123DATABASE.db"


# WebDAV 账号
WEBDAV_USERNAME: "admin"
# WebDAV 密码
WEBDAV_PASSWORD: "123456"
# WebDAV IP (保持默认即可)
WEBDAV_HOST: "0.0.0.0"
# WebDAV 端口
WEBDAV_PORT: 8000


# 123云盘账号
123PAN_USERNAME: "13566666666"
# 123云盘密码
123PAN_PASSWORD: "123456"


# 是否拆分目录
# 当数据库内条数过多(例如超过1000条)时, 在根目录显示所有文件夹, 会导致几乎所有客户端崩溃
# 此时需要额外套一层父文件夹，确保每个文件夹内的文件数目合理可靠
# 默认为True, 除非你知道你在干什么, 否则不要乱改
# 当你使用我提供的数据库时, 务必设置为True
# 当你使用你自己的数据库, 且数据库内条目较少时，可以设置为False
SPLIT_FOLDER: True
```