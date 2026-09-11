#!/usr/bin/env python3
"""把上游插件市场清单拉下来，注入中文描述和图标，输出到 dist/。

为什么要这么做：ZCode 每次刷新市场都会用远端清单覆盖本地，手工加的中文和图标会被冲掉。
与其在本地装监听器，不如让"远端清单本身就是中文的"——ZCode 刷新拿到的就是最终结果，
本地零进程、零脚本，而且目录照样每天自动更新。

三个市场各自的处理：
  - claude-plugins-official / claude-code-plugins
      上游用相对路径（./plugins/xxx）引用插件。URL 类型的市场源没有本地根目录，
      相对路径解析不了，所以统一改写成指向上游仓库的 git-subdir。
  - codex-official
      上游用 {"source":"local","path":"./plugins/xxx"}，同样改写成 openai/plugins 的 git-subdir。

去重保证：
  - 同一插件名在一个清单里出现多次时只保留第一条，其余丢弃并打印出来
  - 按插件名查译文/图标，不会因为查表产生重复条目
  - 输出内容没变化时不重写文件（git 里就不会有噪声提交）
"""
import concurrent.futures as cf
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DIST = os.path.join(HERE, "dist")
UA = {"User-Agent": "zcode-marketplace-zh/1.0"}


def fetch_json(url, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
    raise RuntimeError(f"拉取失败 {url}: {last}")


def strip_dot_slash(p):
    p = (p or "").strip()
    while p.startswith("./"):
        p = p[2:]
    return p


def relative_to_git_subdir(entry, cfg):
    """字符串型相对路径 -> git-subdir 对象。"""
    src = entry.get("source")
    if not isinstance(src, str) or not src.startswith("./"):
        return entry
    entry["source"] = {
        "source": "git-subdir",
        "url": cfg["relative_source_repo"],
        "path": "./" + strip_dot_slash(src),
        "ref": cfg.get("relative_source_ref", "main"),
    }
    return entry


def codex_local_to_git_subdir(entry, cfg):
    src = entry.get("source")
    repo = cfg["relative_source_repo"]
    ref = cfg.get("relative_source_ref", "main")
    if isinstance(src, str) and src.startswith("./"):
        entry["source"] = {
            "source": "git-subdir",
            "url": repo,
            "path": "./" + strip_dot_slash(src),
            "ref": ref,
        }
    elif isinstance(src, dict):
        kind = src.get("source")
        if kind == "local":
            entry["source"] = {
                "source": "git-subdir",
                "url": repo,
                "path": "./" + strip_dot_slash(src.get("path", "")),
                "ref": ref,
            }
        elif kind == "url":
            # 指向外部仓库根目录
            entry["source"] = {"source": "git", "url": src["url"], "ref": ref}
        # git-subdir 原样保留
    return entry


TRANSFORMS = {
    "relative-to-git-subdir": relative_to_git_subdir,
    "codex-local-to-git-subdir": codex_local_to_git_subdir,
}


def build_one(market, cfg, translations, icons):
    manifest = fetch_json(cfg["upstream"])
    plugins = manifest.get("plugins")
    if not isinstance(plugins, list):
        raise ValueError(f"{market}: 上游清单里没有 plugins 数组")

    transform = TRANSFORMS[cfg["source_transform"]]
    seen, dup, out = set(), [], []
    zh_hit = icon_hit = 0

    for raw in plugins:
        if not isinstance(raw, dict):
            continue
        name = (raw.get("name") or "").strip()
        if not name:
            continue
        if name in seen:            # 去重：同名只保留第一条
            dup.append(name)
            continue
        seen.add(name)

        entry = transform(dict(raw), cfg)

        zh = translations.get(name)
        if zh:
            i18n = entry.get("description_i18n")
            if not isinstance(i18n, dict):
                i18n = {}
            i18n["zh-CN"] = zh
            entry["description_i18n"] = i18n
            if entry.get("displayName"):
                dn = entry.get("displayName_i18n")
                if not isinstance(dn, dict):
                    dn = {}
                dn.setdefault("zh-CN", entry["displayName"])
                entry["displayName_i18n"] = dn
            zh_hit += 1

        url = icons.get(name)
        if url and not (entry.get("icon") or "").strip():
            entry["icon"] = url
            icon_hit += 1

        out.append(entry)

    result = {
        "name": cfg["name"],
        "description": cfg["description"],
        "plugins": out,
    }
    if isinstance(manifest.get("metadata"), dict):
        result["metadata"] = manifest["metadata"]

    note = ""
    if dup:
        note = f"，去重丢弃 {len(dup)} 条重复：{sorted(set(dup))}"

    dest = os.path.join(DIST, market + ".json")
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    old = None
    if os.path.exists(dest):
        with open(dest, encoding="utf-8") as f:
            old = f.read()
    if old != serialized:
        with open(dest, "w", encoding="utf-8") as f:
            f.write(serialized)
        changed = "已更新"
    else:
        changed = "无变化"
    print(f"{market}: {len(out)} 个插件，中文 {zh_hit}，图标 {icon_hit}，{changed}{note}")
    return len(out), zh_hit, icon_hit


def main():
    with open(os.path.join(DATA, "sources.json"), encoding="utf-8") as f:
        sources = json.load(f)
    with open(os.path.join(DATA, "icons.json"), encoding="utf-8") as f:
        icons = json.load(f)

    os.makedirs(DIST, exist_ok=True)
    failed = []
    for market, cfg in sources.items():
        tf = os.path.join(DATA, "translations", market + ".json")
        with open(tf, encoding="utf-8") as f:
            translations = json.load(f)
        try:
            build_one(market, cfg, translations, icons.get(market, {}))
        except Exception as e:
            failed.append(market)
            print(f"{market}: 失败 {type(e).__name__}: {e}")

    if failed:
        print(f"\n有 {len(failed)} 个市场构建失败：{failed}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
