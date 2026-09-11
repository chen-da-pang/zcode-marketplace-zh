# ZCode 插件市场中文镜像

把几个上游插件市场清单拉下来、注入中文描述和图标，输出成 ZCode 能直接吃的 URL 源。

## 为什么是这种形式

ZCode 每次刷新市场都会用远端清单覆盖本地缓存，本地手工加的中文和图标会被冲掉。
在本地装监听器/写脚本都不优雅，还会多出一个需要维护的进程。

**换个思路：让远端清单本身就是中文的。** 本地零进程、零脚本，而且目录照样每天自动更新。

## 用法

在 ZCode 的「添加插件市场」里，用这几个地址（`url` 源）：

```
https://raw.githubusercontent.com/chen-da-pang/zcode-marketplace-zh/main/dist/claude-plugins-official.json
https://raw.githubusercontent.com/chen-da-pang/zcode-marketplace-zh/main/dist/claude-code-plugins.json
https://raw.githubusercontent.com/chen-da-pang/zcode-marketplace-zh/main/dist/codex-official.json
```

GitHub 拉不动时的备用地址（jsDelivr CDN，国内更稳）：

```
https://cdn.jsdelivr.net/gh/chen-da-pang/zcode-marketplace-zh@main/dist/claude-plugins-official.json
```

## 注意：`claude-plugins-official` 删不掉

`claude-plugins-official` 和 `zcode-plugins-official` 是 **ZCode 内置市场**，
`zcode.cjs` 里写死在默认列表 `sPt` 里，`ensureDefaultPluginMarketplaces()` 发现缺了会自动补回来。
所以在界面里移除它是徒手的。

正确做法不是删，而是**改指向**：把内置那条的 `source` 从
`{"source":"github","repo":"anthropics/claude-plugins-official"}` 改成
`{"source":"url","url":"<上面的 dist 地址>"}`。ID 不变，已安装的插件不受影响，
刷新时拉到的就是中文镜像。

本地仓库里的 `zh-catalog/switch-sources.py` 就是干这个的（幂等，可反复跑）。
改完需要**完全退出 ZCode（Cmd+Q）再重开**才生效 —— ZCode 会把市场列表缓存在内存里。

| 市场 | 插件数 | 中文 | 图标 | 上游 |
|---|---|---|---|---|
| claude-plugins-official | 294 | 294 | 257 | anthropics/claude-plugins-official |
| claude-code-plugins | 13 | 13 | 11 | anthropics/claude-code |
| codex-official | 65 | 65 | 60 | openai/plugins |

没有图标的那些是上游本来就没提供，会用默认占位图标。

## 自动更新

`.github/workflows/update.yml` 每天 UTC 03:17 跑一次 `build.py`，
把上游最新清单重新拉下来、注入中文和图标、提交到 `dist/`。
也可以手动触发（Actions → 同步插件市场镜像 → Run workflow）。

ZCode 刷新时拿到的是提交后的结果，所以中文和图标不会再被冲掉。

## 两个必要的改写

ZCode 的 `url` 类型市场源没有本地根目录，上游清单里的**相对路径会解析不了**，所以：

- `claude-plugins-official` / `claude-code-plugins`：上游的 `"./plugins/xxx"` 一律改写成
  指向 `anthropics/...` 仓库的 `git-subdir`
- `codex-official`：上游的 `{"source":"local","path":"./plugins/xxx"}` 同样改写成
  `openai/plugins` 的 `git-subdir`

这样插件内容依然从各自仓库实时拉取，不受本仓库更新频率影响。

## 去重

- 同一插件名在一个清单里出现多次时，只保留第一条，其余丢弃并打印
- 按插件名查译文和图标，不会因为查表产生重复条目
- 输出内容没变化时不重写文件 —— `git` 里不会出现噪声提交

## 本地文件

| 文件 | 用途 |
|---|---|
| `build.py` | 生成 `dist/`（CI 和本地都跑这个） |
| `data/sources.json` | 上游地址、市场名、改写规则 |
| `data/translations/*.json` | 372 条中文译文 |
| `data/icons.json` | 插件 → 图标 URL 映射 |
| `dist/*.json` | 产物，ZCode 直接读这些 |
