# Yuque-KnowledgeBase-Export

语雀知识库导出工具：**登录语雀 → 下载知识库（.lakebook）→ 自动转为 Markdown**，也可直接导入本地 `.lakebook`，全程本机处理。

---

## 用户流程

### ① 下载运行

从 [Releases](https://github.com/aihaipeng/Yuque-KnowledgeBase-Export/releases/latest) 下载，无需安装任何依赖：

| 平台 | 文件 | 运行方式 |
| --- | --- | --- |
| Windows | `YuqueExporter.exe` | 双击；SmartScreen 拦截时点「更多信息」→「仍要运行」 |
| macOS | `YuqueExporter.dmg` | 打开 dmg，拖入「应用程序」，首次右键→打开 |
| Linux | `YuqueExporter.AppImage` | `chmod +x YuqueExporter.AppImage && ./YuqueExporter.AppImage` |

### ② 准备知识库（二选一或混用）

- **在线导出**：点「登录语雀」→ 在弹出的浏览器里手动完成登录（账密 / 滑块 / 短信验证码）。登录成功后你名下的知识库自动填入列表，标记为 `[在线]`。登录状态会记住，下次通常免登录。
- **本地导入**（免登录）：点「导入文件」选一个或多个 `.lakebook`；或点「导入目录」自动递归找出所有 `.lakebook`，标记为 `[本地]`。

<img width="2276" height="1393" alt="image" src="https://github.com/user-attachments/assets/80aa6d27-064f-44b8-97f2-de899afc3bf6" />

### ③ 选择条目

在列表中点选要处理的条目，Ctrl / Shift 多选，或点「全选」。选错了点「移除选中」。

### ④ 勾选转换选项（左下角）

- **转为 Markdown**：把 `.lakebook` 转成 Markdown 文件夹（不勾则在线库只下载 `.lakebook`）。
- **下载正文图片到本地**：文档里的远程图片下载到 `attachments/`。
- **生成索引 `_index.md`**：生成导航页，适合 Obsidian 双链浏览。

### ⑤ 导出

点「导出 / 转换选中」，失败项自动重试 3 次；仍失败的等片刻点「重试失败」只重跑失败项。

<img width="979" height="653" alt="image" src="https://github.com/user-attachments/assets/735355b6-a7e5-4f1b-b8cf-0fa3098e950e" />

### ⑥ 拿结果

结果在程序所在目录的 `export/` 文件夹：

| 内容 | 位置 |
| --- | --- |
| 下载的 `.lakebook` | `export/lakebook/` |
| 转换后的 Markdown | `export/markdown/{知识库名}/` |
| 登录会话 | `yuque_profile/` |

每个 Markdown 目录含按序号命名的文档（如 `01-xxx.md`）、可选的 `attachments/` 图片、可选的 `_index.md` 索引。

---

## 常见问题

- **在线导出需要浏览器吗**：需要 Chrome 或 Edge；纯本地转换不需要。
- **图片下载失败**：失败的图片保留原始链接并记录在日志里。
- **数据安全**：内容全部本机处理，不上传第三方。

---

## 开发者

```bash
git clone https://github.com/aihaipeng/Yuque-KnowledgeBase-Export.git
cd Yuque-KnowledgeBase-Export
python -m pip install -r requirements.txt   # DrissionPage / markdownify / pyyaml
python yuque_export.py                       # 也可双击 Start.bat
```

- `yuque_export.py`：主程序（GUI + 登录 / 下载 / 调度）
- `converter.py`：`.lakebook` → Markdown 转换核心
- 发布：推送 `v*` 标签，GitHub Actions 自动构建三平台并发布 Release；本地打包用 `Build-Windows.bat`
