# 汉化机制详解

> 面向想自己改词条、或者想搞明白"为什么有些地方不翻译"的人。

## 一、整体链路

```
Antigravity.exe (Electron 主进程)
  └─ 读 resources\app.asar
       ├─ dist/*.js        ← Electron 主进程代码（菜单、托盘、安装向导、窗口…）
       └─ 注入引擎到网页界面（webview）
            └─ engine.js + zh_data.json
                 └─ MutationObserver 盯着 DOM
                      ├─ 文本节点           → translateString()
                      ├─ aria-label/title/placeholder → translateAttrs()
                      └─ 路由切换 / Shadow DOM / 焦点恢复 兜底
```

**界面本身不是 asar 里的**：`app.asar` 只有 Electron 主进程的 `dist/*`。
真正的网页界面由 **语言服务器**（`resources\bin\language_server.exe`）提供，
在 `https://127.0.0.1:<随机端口>/` 上跑，单文件 `main.js`（约 11MB，**没有代码分割**）。

## 二、词典（`zh_data.json`）

| 字段 | 匹配方式 | 注意 |
|---|---|---|
| `exact` | 整句精确匹配 | 主力条目 |
| `prefix` | 前缀命中 | **必须 ≥16 字符**才会被索引（`if (k.length >= 16)`），短前缀无效 |
| `core` | 核心词分词 | 只对 **≤3 词**的短文本生效，且原文不含中文 |
| `regex` | 正则替换 | **在词级替换之前执行，吃的是原文** → 处理动态文案的首选 |
| `menuMap` | 原生菜单项 | File / Edit / View / Help… |
| `staticPatches` | 直接改 asar 里 7 个文件 | tray.js / main.js / ipcHandlers.js / updater.js / ideInstall/wizardHtml.js / webauthn.js / cablev2.js |
| `exempt` | 命中就整条跳过 | |
| `mentionCategories` | 斜杠命令菜单白名单 | |

### 翻译管线的顺序（`engine.js` 的 `pipeline()`）

```
0. exempt 命中 → 原样返回
1. exact 精确
2. regex 动态规则        ← 原文参与
3. exact 忽略大小写
4. exact 忽略空白差异
5. exact 去尾部标点
6. prefix 前缀
7. core 核心词分词
```

> 因为 **regex 在词级替换之前**，所以 "Run X finished" 这类动态句子
> 必须用 regex 写；等它被 core 拆成 "运行 X 完成" 就来不及了。

## 三、引擎**故意不翻**的地方

| 位置 | 原因 |
|---|---|
| `script` / `style` / `noscript` / `kbd` / `samp` / `var` / `textarea` | 不是展示文本 |
| `input` / `contenteditable` / `role=textbox` | 用户输入 |
| `monaco-editor` / `hljs` / `shiki` / `prism` / `codemirror` / `codeblock` / `line-content` / `view-line` | 代码 |
| `user-message` / `chat-message-view` / `stream-markdown*` / `thought-*` / `conversation-container` | 用户与模型的消息体（翻译会篡改内容） |
| `input-area` / `chat-input` / `cursor-text` | 输入区 |
| 斜杠命令菜单 | 只有 `mentionCategories` 白名单放行 |
| 带 `data-ag-localization-skip` 的元素 | 页面自己声明的禁区 |

**例外**：执行步骤的药丸标签（`Explored` / `Ran` / `Edited` / `Viewed` …）
如果整段文本 ≤25 字符且正好匹配这些词，引擎会**放行**翻译。
所以 "Explored files, ran commands, edited files" 是能翻的——它只是**词典里没有**。

## 四、为什么官方更新后英文回来了

官方更新会整体替换 `resources\app.asar`（引擎和词典都在里面）→ 界面立刻回到英文。
同时官方安装器也会删掉 `app.asar.bak`（上游工具用来"还原官方原版"的备份）。

于是修复要两件事：

1. **重新打补丁**：`python localize.py apply --yes`（约 30 秒）
2. **自动做这件事**：本仓库的 `ag-han-huajin-guard.ps1`
   - 比对 `app.asar` 的 SHA256 和上次成功汉化后记录的哈希
   - 不同 → 官方更新过 → 需要重新汉化
   - IDE 没开 → 立刻汉化
   - IDE 正开 → **绝不杀它**（会丢未保存的工作）→ 布下 `ag-han-huajin-watcher.ps1`
     守望者轮询 IDE 进程，**你一关掉它就在几秒内补好** → 下次打开就是中文

## 五、怎么找"漏译"的文案

**别静态扫 asar**——里面只有主进程代码，界面文案不在那儿；
就算去扫 `language_server.exe` 也有 95% 以上是 CSS 类名和 Java 类名。

正确做法（用 CDP 驱动正在运行的 IDE）：

1. **截图定位**
   ```js
   // 通过 DevToolsActivePort 连上 IDE 的渲染进程
   await Page.captureScreenshot({ format: 'png' })
   ```
2. **收集可见英文**（遍历 DOM，取文本节点 + `aria-label`/`title`/`placeholder`）
3. **排除用户内容**：项目名、会话名、提交信息、文件路径、代码块
4. **剩下的就是词典缺的**——因为界面已经被引擎处理过了，仍显示英文的必然是没覆盖到的
5. 写进 `patches/zh_data.extra.json` → 重新 `apply --yes`

### 选 exact 还是 regex

| 情况 | 用 |
|---|---|
| 整句固定 | `exact` |
| 含数字/名字的模板（`Explored 3 files`） | `regex`：`^Explored (\d+) files?$` → `浏览了 $1 个文件` |
| 句首固定、后面跟动态内容 | `prefix`（**长度 ≥16**） |
| 单个常见词 | `core` 或 `exact` |

## 六、坑

1. **PowerShell 5.1 按 ANSI 读 `.ps1`**（没有 BOM 时）→ 脚本里出现中文会报
   "字符串缺少终止符" 之类的解析错误。**脚本一律纯 ASCII**，中文路径用通配符找。
2. **`localize.py apply --yes` 不会启动 IDE**（只有交互模式才问"是否立即启动"），
   所以可以安全地接在启动器前面——启动仍由你的启动器负责，能带上代理参数。
3. **词典会被上游工具更新覆盖** → 增量词条单独存一份（本仓库的
   `patches/zh_data.extra.json`），更新后重新合并即可。
