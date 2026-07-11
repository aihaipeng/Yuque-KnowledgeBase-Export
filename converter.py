# -*- coding: utf-8 -*-
"""lakebook -> Markdown 转换核心：解包、转换、图片本地化、生成索引。"""
import os, re, json, hashlib, tarfile, urllib.request
import yaml
from markdownify import markdownify as md

IMG_RE = re.compile(r'!\[(.*?)\]\((https?://[^)\s]+)\)')


class ConversionCancelled(Exception):
    """Raised when a user cancels an active conversion."""


def safe_name(name):
    return re.sub(r'[\\/:*?"<>|]', '_', (name or '').strip()) or 'untitled'


def _find_root(tmp):
    """定位含 $meta.json 的知识库目录。"""
    for base, _, files in os.walk(tmp):
        if '$meta.json' in files:
            return base
    return None


def _parse_toc(meta_path):
    raw = json.load(open(meta_path, encoding='utf-8'))
    meta = json.loads(raw['meta'])
    toc = yaml.safe_load(meta['book']['tocYml'])
    items, order = [], 0
    for node in toc:
        if node.get('type') != 'DOC':
            continue
        order += 1
        items.append((order, node.get('title', 'untitled'), node.get('url', '')))
    return items


def _download_img(url, folder):
    ext = os.path.splitext(url.split('?')[0])[1] or '.png'
    name = hashlib.md5(url.encode()).hexdigest()[:16] + ext
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as r, open(path, 'wb') as f:
            f.write(r.read())
    return name


def _localize(text, att_dir, report, check_cancelled):
    def repl(m):
        check_cancelled()
        alt, url = m.group(1), m.group(2)
        try:
            name = _download_img(url, att_dir)
            return f'![{alt}](attachments/{name})'
        except Exception as e:
            report(f'Image download failed: {url[:50]}... ({e})')
            return m.group(0)
    return IMG_RE.sub(repl, text)


def _safe_extract(tar, dest):
    """防止路径穿越的安全解包。"""
    for member in tar.getmembers():
        p = os.path.realpath(os.path.join(dest, member.name))
        if not p.startswith(os.path.realpath(dest) + os.sep):
            raise ValueError(f'Unsafe archive path: {member.name}')
    tar.extractall(dest)


def convert(lakebook_path, outdir, book_title='Knowledge Base',
            localize_images=True, make_index=True, logger=None, cancel_event=None):
    """执行完整转换。logger 可接收转换过程中的实时文本日志。"""
    import tempfile, shutil
    log, tmp = [], tempfile.mkdtemp()

    def report(message):
        log.append(message)
        if logger:
            logger(message)

    def check_cancelled():
        if cancel_event and cancel_event.is_set():
            raise ConversionCancelled('Conversion cancelled by user.')

    try:
        check_cancelled()
        report(f'Extracting: {os.path.basename(lakebook_path)}')
        with tarfile.open(lakebook_path) as t:
            _safe_extract(t, tmp)
        root = _find_root(tmp)
        if not root:
            raise ValueError('Missing $meta.json: this is not a valid lakebook file.')

        items = _parse_toc(os.path.join(root, '$meta.json'))
        report(f'Found {len(items)} document(s).')
        os.makedirs(outdir, exist_ok=True)
        att_dir = os.path.join(outdir, 'attachments')
        docs, img_count = 0, 0

        for order, title, slug in items:
            check_cancelled()
            doc_file = os.path.join(root, slug + '.json')
            if not os.path.exists(doc_file):
                report(f'Skipped (no content): {title}')
                continue
            report(f'Converting {order}/{len(items)}: {title}')
            doc = json.load(open(doc_file, encoding='utf-8'))['doc']
            html = doc.get('body') or doc.get('body_draft') or ''
            body = re.sub(r'\n{3,}', '\n\n',
                          md(html, heading_style='ATX', bullets='-')).strip()
            if localize_images and IMG_RE.search(body):
                os.makedirs(att_dir, exist_ok=True)
                before = len(os.listdir(att_dir))
                body = _localize(body, att_dir, report, check_cancelled)
                img_count += len(os.listdir(att_dir)) - before
            fname = f'{order:02d}-{safe_name(title)}.md'
            open(os.path.join(outdir, fname), 'w', encoding='utf-8').write(
                f'# {title}\n\n{body}\n')
            docs += 1

        if make_index:
            _write_index(outdir, book_title, docs)
            report('Created index: _index.md')
        report(f'Complete: {docs} document(s), {img_count} image(s).')
        return {'docs': docs, 'images': img_count, 'log': log}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _write_index(outdir, book_title, count):
    files = sorted(f for f in os.listdir(outdir)
                   if f.endswith('.md') and f != '_index.md')
    lines = [f'# {book_title}', '', f'> {count} document(s) · Exported from Yuque',
             '', '## Contents', '']
    for f in files:
        stem = f[:-3]
        title = re.sub(r'^\d+[-\s]*', '', stem)
        lines.append(f'- [[{stem}|{title}]]')
    open(os.path.join(outdir, '_index.md'), 'w',
         encoding='utf-8').write('\n'.join(lines) + '\n')
