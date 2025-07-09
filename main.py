import uvicorn
import yaml
from fastapi import FastAPI
from webdav_router import router as webdav_router
from file_system import vfs

# 读取配置文件
with open("settings.yaml", "r", encoding="utf-8") as f:
    settings_data = yaml.safe_load(f.read())

app = FastAPI(
    title="123Pan Unlimited WebDAV",
    description="将 123Pan Unlimited Share 的数据库挂载为WebDAV服务",
    version="1.0.0",
    docs_url=None, 
    redoc_url=None,
)

app.include_router(webdav_router)

if __name__ == "__main__":
    uvicorn.run(
        app, 
        host=settings_data.get("WEBDAV_HOST"), 
        port=settings_data.get("WEBDAV_PORT"), 
        # debug 参数
        # log_level="info",
        # access_log=True
        # 发布参数
        log_level="warning",
        access_log=False
    )