# [123云盘](https://www.123pan.com) 无限制挂载工具（编译教程文档）

## 目录

- [123云盘 无限制挂载工具（编译教程文档）](#123云盘-无限制挂载工具编译教程文档)
  - [目录](#目录)
  - [一、创建全新的 `Python` 虚拟环境](#一创建全新的-python-虚拟环境)
  - [二、进入虚拟环境](#二进入虚拟环境)
  - [三、安装依赖](#三安装依赖)
  - [四、安装 `nuitka` 编译工具](#四安装-nuitka-编译工具)
  - [五、编译项目](#五编译项目)
  - [六、编译成功](#六编译成功)
  - [七、运行](#七运行)

## 一、创建全新的 `Python` 虚拟环境

```shell
conda create -n pan python=3.13
```

## 二、进入虚拟环境

```shell
conda activate pan
```

## 三、安装依赖

```shell
pip install -r requirements.txt
```

## 四、安装 `nuitka` 编译工具

```shell
pip install nuitka
```

## 五、编译项目

```shell
nuitka --standalone --onefile main.py
```

## 六、编译成功

- 编译的文件位于`123Pan-Unlimited-WebDAV` 文件夹下的 `main.exe`

## 七、运行

- 直接运行 `main.exe` 即可。