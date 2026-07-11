# yuque-exporter-v2

语雀知识库一站式导出工具：**登录语雀 → 下载知识库（.lakebook）→ 自动转换为 Markdown**，也支持直接导入本地已有的 `.lakebook` 文件转换。可视化界面，左侧操作、右侧实时日志。

## 功能

- **在线导出**：浏览器手动登录语雀（账密 / 滑块 / 短信验证码），自动拉取知识库列表，选中后下载为 `.lakebook`。
- **本地导入**：无需登录，直接导入本地的 `.lakebook` 文件或整个目录（自动递归查找）。
- **自动转 Markdown**：下载或导入后转换为 Markdown 文件夹，可选下载正文图片到本地、生成 `_index.md` 索引（适合 Obsidian）。
- **失败重试**：下载失败自动重试 3 次；处理结束后可一键「重试失败」，只重跑失败项。
- **会话持久化**：登录状态保存在 `yuque_profile/`，下次运行若仍有效则免登录。

## 使用步骤

### 第 1 步：启动程序

**Windows（最简单）**：双击 `dist/YuqueExporter.exe` 即可，无需安装 Python。首次运行若被 SmartScreen 拦截，点「更多信息」→「仍要运行」。

> 程序会在dist/目录生成 `export/`、`yuque_profile/`

**Windows / macOS / Linux（从源码）**：需先装 Python 3.10+，然后：

```bash
python -m pip install -r requirements.txt   # 安装依赖（首次）
python yuque_export.py                       # 启动；macOS/Linux 用 python3
```

Windows 也可直接双击 `Start.bat`（自动装依赖并启动）。macOS 用 Homebrew 装的 Python 若报 `No module named '_tkinter'`，补装 `brew install python-tk`。

启动后会出现主窗口：左侧是操作区，右侧是实时日志。

### 第 2 步：准备要处理的知识库

两种来源，可任选或混用：

- **在线导出**：点左侧「登录语雀」，弹出浏览器后手动完成登录（账号密码 → 拖动滑块 → 短信验证码）。登录成功后，你名下的知识库会自动填入列表，标记为 `[在线]`。（会话会记住，下次通常免登录。）
- **本地导入**（无需登录）：点「导入文件」选择一个或多个 `.lakebook` 文件；或点「导入目录」选一个文件夹，自动递归找出里面所有 `.lakebook`。导入的文件标记为 `[本地]`。
<img width="2276" height="1393" alt="image" src="https://github.com/user-attachments/assets/80aa6d27-064f-44b8-97f2-de899afc3bf6" />
<img width="2282" height="1397" alt="image" src="https://github.com/user-attachments/assets/735355b6-a7e5-4f1b-b8cf-0fa3098e950e" />

### 第 3 步：选择条目

在列表中点选要处理的条目，按住 Ctrl / Shift 可多选，或点「全选」。选错了可选中后点「移除选中」。


### 第 4 步：设置转换选项

勾选左下角的选项：

- **转为 Markdown**：把下载 / 导入的 `.lakebook` 转成 Markdown 文件夹（不勾则在线库只下载 `.lakebook` 不转换）。
- **下载正文图片到本地**：把文档里的远程图片下载到 `attachments/` 文件夹。
- **生成索引 `_index.md`**：生成一个导航页，适合 Obsidian 双链浏览。

### 第 5 步：开始处理

点「导出 / 转换选中」。右侧日志实时显示每一步进度。处理结束会汇总成功 / 失败数量，并打印输出位置。

- 在线条目：触发导出 → 下载 `.lakebook` → （可选）转 Markdown。
- 本地条目：直接转 Markdown。
<img width="979" height="653" alt="image" src="https://github.com/user-attachments/assets/d7d126e4-d536-4dc8-93f0-c5407363eeda" />


### 第 6 步：查看结果与重试

处理完成后，到输出目录查看结果（见下方「输出目录」）。若有条目失败（如网络中断），可以停顿片刻重试

## 输出目录

| 内容 | 位置 |
| --- | --- |
| 下载的 `.lakebook` | `export/lakebook/` |
| 转换后的 Markdown | `export/markdown/{知识库名}/` |
| 浏览器会话 | `yuque_profile/` |
<img width="1113" height="626" alt="image" src="https://github.com/user-attachments/assets/5df49851-33b2-4a3f-a9b6-3ef5d1c8ad85" />


每个 Markdown 目录含按序号命名的文档（如 `01-xxx.md`）、可选的 `attachments/` 图片文件夹、可选的 `_index.md` 索引。

## 重新打包 exe

修改源码后，双击 `Build-Windows.bat`（或运行其中的 PyInstaller 命令）重新生成 `dist/YuqueExporter.exe`。

## 项目结构

```
yuque_export.py       # 主程序：可视化界面 + 登录 / 下载 / 调度
converter.py          # .lakebook → Markdown 转换核心
Start.bat             # 从源码启动
Build-Windows.bat     # 打包为单文件 exe
requirements.txt      # 依赖：DrissionPage / markdownify / pyyaml
```

## 注意事项

- **在线导出需要浏览器**：依赖 Chrome / Edge 驱动真实浏览器登录，exe 不含浏览器（Windows 自带 Edge 即可）。纯本地转换则不需要浏览器。
- 图片下载需要网络；无法下载的图片会保留原始链接并记录在日志中。
- 程序不会上传任何 `.lakebook` 内容到第三方，全部在本机处理。

