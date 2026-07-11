#!/usr/bin/env python3
"""语雀知识库导出 —— 可视化界面版。

左侧：登录按钮、知识库列表、导出按钮。
右侧：实时日志。
浏览器手动登录（拖滑块 / 短信验证码），会话持久化到 ./yuque_profile。
"""
import json
import os
import re
import sys
import time
import queue
import threading
import urllib.request
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog
from DrissionPage import ChromiumPage, ChromiumOptions

import converter  # lakebook -> Markdown 转换核心（本项目模块）

HOME = "https://www.yuque.com"
LOGIN_URL = "https://www.yuque.com/login"
PROFILE_DIR = "yuque_profile"
EXPORT_DIR = os.path.join("export", "lakebook")     # 下载的 .lakebook 存放目录
MARKDOWN_DIR = os.path.join("export", "markdown")   # 转换后的 Markdown 存放目录
DOWNLOAD_RETRIES = 3        # 下载失败自动重试次数


# 浏览器可执行文件候选路径：按操作系统区分，优先 Chrome，回退到 Edge。
def _browser_candidates():
    if sys.platform.startswith("win"):
        return [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
    if sys.platform == "darwin":  # macOS
        return [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    # Linux
    return [
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/microsoft-edge",
    ]


def find_browser():
    """返回第一个存在的浏览器路径，找不到返回 None（交由 DrissionPage 自动探测）。"""
    for p in _browser_candidates():
        if os.path.exists(p):
            return p
    return None


def make_page():
    co = ChromiumOptions()
    co.set_user_data_path(PROFILE_DIR)   # 持久化会话，避免每次都登录
    browser = find_browser()
    if browser:
        co.set_browser_path(browser)     # 显式指定 Chrome / Edge
    return ChromiumPage(co)


def safe_run_js(page, js, *args, retries=6):
    """安全执行 JS：先等页面加载完，遇到"页面被刷新/加载中"异常时自动重试。

    页面在登录跳转期间会频繁刷新，直接 run_js 可能抛异常。返回结果或 None。
    """
    for _ in range(retries):
        try:
            page.wait.doc_loaded(timeout=10)
        except Exception:
            pass
        try:
            return page.run_js(js, *args)
        except Exception:
            # 页面正在刷新/跳转，稍候重试
            time.sleep(1)
    return None


def api_get(page, path):
    """在当前页面上下文用同步 XHR 调内部接口，自动带上登录 cookie。

    不改变当前页面。返回解析后的 dict/list，失败返回 None。
    """
    js = """
    try {
        var xhr = new XMLHttpRequest();
        xhr.open('GET', arguments[0], false);
        xhr.setRequestHeader('Accept', 'application/json');
        xhr.send();
        return JSON.stringify({status: xhr.status, body: xhr.responseText});
    } catch (e) { return JSON.stringify({status: 0, body: String(e)}); }
    """
    raw = safe_run_js(page, js, HOME + path)
    if not raw:
        return None
    try:
        resp = json.loads(raw)
    except Exception:
        return None
    if resp.get("status") != 200:
        return None
    try:
        return json.loads(resp.get("body", "")).get("data")
    except Exception:
        return None


def check_login(page):
    """返回已登录用户 dict，未登录返回 None。"""
    me = api_get(page, "/api/mine")
    if me and me.get("id"):
        return me
    return None


def wait_login(page, log, timeout=300):
    """打开登录页，等待用户手动登录，轮询确认。log 为日志回调。"""
    # 先看持久化会话是否还有效
    page.get(HOME)
    me = check_login(page)
    if me:
        log(f"检测到已有会话，直接登录：{me.get('name')}（{me.get('login')}）")
        return me

    page.get(LOGIN_URL)
    log("请在打开的浏览器窗口中手动完成登录：账号密码 → 拖动滑块 → 短信验证码")
    log(f"正在自动检测登录状态，最长等待 {timeout} 秒……")

    deadline = time.time() + timeout
    while time.time() < deadline:
        me = check_login(page)
        if me:
            log(f"登录成功：{me.get('name')}（{me.get('login')}）")
            return me
        time.sleep(2)
    log("等待登录超时。")
    return None


def get_books(page):
    """拉取当前账号的知识库列表，返回扁平列表。

    优先用 /api/mine/book_stacks（分组结构），失败回退 /api/mine/personal_books。
    """
    books = []
    stacks = api_get(page, "/api/mine/book_stacks")
    if stacks:
        for group in stacks:
            for b in group.get("books", []):
                books.append(b)
    if not books:
        flat = api_get(page, "/api/mine/personal_books")
        if flat:
            books = flat
    # 去重（按 id）
    seen, uniq = set(), []
    for b in books:
        bid = b.get("id")
        if bid and bid not in seen:
            seen.add(bid)
            uniq.append(b)
    return uniq


def get_csrf_token(page):
    """从 yuque_ctoken cookie 读取 CSRF token，用于写接口。"""
    raw = safe_run_js(page, "return document.cookie;") or ""
    m = re.search(r"yuque_ctoken=([^;]+)", raw)
    return m.group(1) if m else ""


def request_export(page, book_id, token, fmt="lakebook"):
    """POST /api/books/{id}/export，返回响应 dict（含 state / url）。"""
    js = """
    try {
        var xhr = new XMLHttpRequest();
        xhr.open('POST', arguments[0], false);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.setRequestHeader('x-csrf-token', arguments[1]);
        xhr.send(arguments[2]);
        return JSON.stringify({status: xhr.status, body: xhr.responseText});
    } catch (e) { return JSON.stringify({status: 0, body: String(e)}); }
    """
    url = f"{HOME}/api/books/{book_id}/export"
    payload = json.dumps({"type": fmt})
    raw = safe_run_js(page, js, url, token, payload)
    if not raw:
        return None
    try:
        resp = json.loads(raw)
        if resp.get("status") != 200:
            return None
        return json.loads(resp.get("body", "")).get("data")
    except Exception:
        return None


def export_book(page, book, token, log, timeout=120,
                to_markdown=True, localize_images=True, make_index=True):
    """触发单个知识库导出、下载 .lakebook，成功后可自动转 Markdown。

    返回 (lakebook_path, markdown_dir)；失败对应项为 None。
    """
    book_id = book.get("id")
    name = book.get("name") or str(book_id)
    log(f"导出《{name}》…")

    deadline = time.time() + timeout
    url = None
    while time.time() < deadline:
        data = request_export(page, book_id, token)
        if not data:
            log(f"  《{name}》触发导出失败（token 失效或接口有变）。")
            return None, None
        state = data.get("state")
        if state == "success" and data.get("url"):
            url = data["url"]
            break
        # pending / processing：等待后重试
        log(f"  服务端打包中（state={state}），等待…")
        time.sleep(3)
    if not url:
        log(f"  《{name}》等待导出超时。")
        return None, None

    path = download_lakebook(url, name, log)
    if not path:
        return None, None

    md_dir = None
    if to_markdown:
        md_dir = convert_to_markdown(path, name, log, localize_images, make_index)
    return path, md_dir


def convert_to_markdown(lakebook_path, name, log,
                        localize_images=True, make_index=True):
    """调用已有 converter 把 .lakebook 转为 Markdown 目录，返回输出目录或 None。"""
    outdir = unique_dir(os.path.join(MARKDOWN_DIR, sanitize(name)))
    log(f"  转换《{name}》为 Markdown → {outdir}")
    try:
        result = converter.convert(
            lakebook_path, outdir, book_title=name,
            localize_images=localize_images, make_index=make_index,
            logger=lambda m: log("    " + m))
        log(f"  转换完成：{result['docs']} 篇文档，{result['images']} 张图片。")
        return outdir
    except Exception as e:
        log(f"  转换失败：{e}")
        return None


def unique_dir(path):
    """若目录已存在，追加 (2)/(3)… 避免覆盖。"""
    if not os.path.exists(path):
        return path
    i = 2
    while os.path.exists(f"{path} ({i})"):
        i += 1
    return f"{path} ({i})"


def sanitize(name):
    """清理文件名中的非法字符。"""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "book"


def download_lakebook(url, name, log, retries=DOWNLOAD_RETRIES):
    """下载 OSS 签名 URL 到 EXPORT_DIR，失败自动重试，返回路径或 None。"""
    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(EXPORT_DIR, sanitize(name) + ".lakebook")
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as f:
                f.write(r.read())
            size = os.path.getsize(path)
            log(f"  已保存：{path}（{size/1024:.0f} KB）")
            return path
        except Exception as e:
            log(f"  下载失败（第 {attempt}/{retries} 次）：{e}")
            if attempt < retries:
                time.sleep(2 * attempt)   # 递增退避
    log(f"  《{name}》下载重试 {retries} 次均失败。")
    return None


class ExporterApp:
    """语雀导出可视化界面。"""

    def __init__(self, root):
        self.root = root
        self.page = None          # 浏览器实例（登录后创建）
        # 列表条目：统一容纳「在线知识库」和「本地 lakebook」
        #   在线：{"kind":"online", "book":{...}}
        #   本地：{"kind":"local",  "path":"x.lakebook", "name":"x"}
        self.items = []
        self.failed = []          # 上次处理失败的条目，供"重试失败"
        self.logged_in = False
        self.busy = False         # 是否有后台任务在跑
        self.log_queue = queue.Queue()

        root.title("语雀知识库导出")
        root.geometry("900x560")
        self._build_ui()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._drain_log)

    def _build_ui(self):
        # 左侧操作栏
        left = ttk.Frame(self.root, padding=10)
        left.pack(side="left", fill="y")

        self.login_btn = ttk.Button(left, text="登录语雀（在线导出）",
                                     command=self.on_login)
        self.login_btn.pack(fill="x")

        # 本地导入：无需登录即可用
        imp = ttk.Frame(left)
        imp.pack(fill="x", pady=(6, 0))
        ttk.Button(imp, text="导入文件", command=self.on_import_files).pack(
            side="left", fill="x", expand=True)
        ttk.Button(imp, text="导入目录", command=self.on_import_dir).pack(
            side="left", fill="x", expand=True, padx=(6, 0))

        ttk.Label(left, text="知识库 / 本地文件（可多选）").pack(
            anchor="w", pady=(12, 2))
        self.listbox = tk.Listbox(left, selectmode="extended", width=34, height=16)
        self.listbox.pack(fill="both", expand=True)

        row = ttk.Frame(left)
        row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="全选", command=self.on_select_all).pack(
            side="left", fill="x", expand=True)
        ttk.Button(row, text="移除选中", command=self.on_remove).pack(
            side="left", fill="x", expand=True, padx=(6, 0))

        # 转换选项
        self.var_md = tk.BooleanVar(value=True)
        self.var_img = tk.BooleanVar(value=True)
        self.var_idx = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="转为 Markdown（在线库下载后转换）",
                        variable=self.var_md).pack(anchor="w", pady=(10, 0))
        ttk.Checkbutton(left, text="下载正文图片到本地",
                        variable=self.var_img).pack(anchor="w")
        ttk.Checkbutton(left, text="生成索引 _index.md",
                        variable=self.var_idx).pack(anchor="w")

        self.export_btn = ttk.Button(left, text="导出 / 转换选中",
                                     command=self.on_export)
        self.export_btn.pack(fill="x", pady=(10, 0))
        self.retry_btn = ttk.Button(left, text="重试失败", state="disabled",
                                    command=self.on_retry)
        self.retry_btn.pack(fill="x", pady=(6, 0))

        # 右侧日志
        right = ttk.Frame(self.root, padding=(0, 10, 10, 10))
        right.pack(side="right", fill="both", expand=True)
        ttk.Label(right, text="运行日志").pack(anchor="w")
        self.log_view = scrolledtext.ScrolledText(right, state="disabled",
                                                   wrap="word", font=("Consolas", 10))
        self.log_view.pack(fill="both", expand=True)

    # ---- 日志：线程安全，后台线程写队列，主线程渲染 ----
    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_queue.put(f"[{ts}] {msg}")

    def _drain_log(self):
        while not self.log_queue.empty():
            line = self.log_queue.get_nowait()
            self.log_view.configure(state="normal")
            self.log_view.insert("end", line + "\n")
            self.log_view.see("end")
            self.log_view.configure(state="disabled")
        self.root.after(100, self._drain_log)

    def _run_bg(self, fn):
        """在后台线程跑阻塞任务，避免界面卡死。"""
        if self.busy:
            self.log("有任务正在运行，请稍候…")
            return
        self.busy = True
        threading.Thread(target=self._bg_wrapper, args=(fn,), daemon=True).start()

    def _bg_wrapper(self, fn):
        try:
            fn()
        except Exception as e:
            self.log(f"出错：{e}")
        finally:
            self.busy = False

    # ---- 事件处理 ----
    def on_login(self):
        self._run_bg(self._do_login)

    def _do_login(self):
        if self.page is None:
            self.log("正在启动浏览器…")
            self.page = make_page()
        me = wait_login(self.page, self.log)
        if not me:
            return
        self.logged_in = True
        self.log("正在拉取知识库列表…")
        books = get_books(self.page)
        if not books:
            self.log("未获取到知识库，接口路径可能有变。")
            return
        self.log(f"已获取 {len(books)} 个知识库。")
        # 去重后加入列表（避免重复登录重复添加）
        existing = {it["book"]["id"] for it in self.items if it["kind"] == "online"}
        new = [b for b in books if b.get("id") not in existing]
        self.root.after(0, lambda: self._add_online(new))

    def _add_online(self, books):
        for b in books:
            self.items.append({"kind": "online", "book": b})
        self._refresh_listbox()

    def _refresh_listbox(self):
        """按 self.items 重绘列表框。"""
        self.listbox.delete(0, "end")
        for it in self.items:
            if it["kind"] == "online":
                b = it["book"]
                cnt = b.get("items_count", b.get("doc_count", "?"))
                self.listbox.insert("end", f"[在线] {b.get('name')}  (文档数={cnt})")
            else:
                self.listbox.insert("end", f"[本地] {it['name']}.lakebook")

    def on_select_all(self):
        self.listbox.select_set(0, "end")

    def on_remove(self):
        for i in sorted(self.listbox.curselection(), reverse=True):
            del self.items[i]
        self._refresh_listbox()

    # ---- 本地导入 ----
    def on_import_files(self):
        paths = filedialog.askopenfilenames(
            title="选择 .lakebook 文件",
            filetypes=[("Lakebook 文件", "*.lakebook"), ("所有文件", "*.*")])
        self._add_local(paths)

    def on_import_dir(self):
        folder = filedialog.askdirectory(title="选择包含 .lakebook 的目录")
        if not folder:
            return
        found = []
        for base, _, files in os.walk(folder):
            for fn in files:
                if fn.lower().endswith(".lakebook"):
                    found.append(os.path.join(base, fn))
        self._add_local(found)

    def _add_local(self, paths):
        known = {it["path"] for it in self.items if it["kind"] == "local"}
        added = 0
        for p in paths:
            p = os.path.abspath(p)
            if not p.lower().endswith(".lakebook") or p in known:
                continue
            name = os.path.splitext(os.path.basename(p))[0]
            self.items.append({"kind": "local", "path": p, "name": name})
            known.add(p)
            added += 1
        if added:
            self._refresh_listbox()
            self.log(f"已导入 {added} 个本地 .lakebook 文件。")
        else:
            self.log("未发现可导入的 .lakebook 文件。")

    def on_export(self):
        idxs = self.listbox.curselection()
        if not idxs:
            self.log("请先在列表中选择要处理的条目。")
            return
        selected = [self.items[i] for i in idxs]
        self._run_bg(lambda: self._do_export(selected))

    def on_retry(self):
        if not self.failed:
            self.log("没有可重试的失败条目。")
            return
        self.log(f"重试上次失败的 {len(self.failed)} 个条目…")
        self._run_bg(lambda: self._do_export(list(self.failed)))

    def _do_export(self, selected):
        # 在线条目需要 token，先备好
        online_exist = any(it["kind"] == "online" for it in selected)
        token = None
        if online_exist:
            if not self.logged_in or self.page is None:
                self.log("在线知识库需先「登录语雀」。将跳过在线条目。")
            else:
                token = get_csrf_token(self.page)
                if not token:
                    self.log("未取到 CSRF token，将跳过在线条目。")

        failed = []
        for it in selected:
            if not self._process_item(it, token):
                failed.append(it)

        self.failed = failed
        ok = len(selected) - len(failed)
        self.log(f"处理完成：{ok}/{len(selected)} 成功，{len(failed)} 失败。")
        if failed:
            self.log("失败条目：" + "、".join(self._item_label(it) for it in failed))
        self.log(f"输出位置：lakebook → {os.path.abspath(EXPORT_DIR)}")
        self.log(f"          markdown → {os.path.abspath(MARKDOWN_DIR)}")
        # 回主线程更新重试按钮状态
        self.root.after(0, lambda: self.retry_btn.configure(
            state="normal" if failed else "disabled"))

    def _process_item(self, it, token):
        """处理单个条目，成功返回 True，失败返回 False。"""
        if it["kind"] == "local":
            self.log(f"转换本地文件《{it['name']}》…")
            return bool(convert_to_markdown(
                it["path"], it["name"], self.log,
                self.var_img.get(), self.var_idx.get()))
        # 在线
        if not token:
            return False
        path, md_dir = export_book(
            self.page, it["book"], token, self.log,
            to_markdown=self.var_md.get(),
            localize_images=self.var_img.get(),
            make_index=self.var_idx.get())
        if not path:
            return False
        # 勾选了转换却没转出，也算失败
        if self.var_md.get() and not md_dir:
            return False
        return True

    def _item_label(self, it):
        return (f"[在线]{it['book'].get('name')}" if it["kind"] == "online"
                else f"[本地]{it['name']}")

    def _on_close(self):
        if self.page is not None:
            try:
                self.page.quit()
            except Exception:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    ExporterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
