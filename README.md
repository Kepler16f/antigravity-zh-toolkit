# Antigravity 中文增强工具箱

> 让 [Antigravity IDE](https://antigravity.google) 的中文界面**更完整**，并且在**官方更新后自动恢复**。

本仓库只包含**我额外做的部分**：

| 内容 | 说明 |
|---|---|
| `patches/zh_data.extra.json` | 我补充的词条（2.30.0 新增界面、代理动作气泡、快捷键区、插件市场、无障碍标签……） |
| `scripts/ag-han-huajin-guard.ps1` | **守护脚本**：检测到官方更新覆盖了 `app.asar` → 自动重新汉化 |
| `scripts/ag-han-huajin-watcher.ps1` | **退出守望者**：更新时 IDE 正开着 → 你一关掉它就在几秒内自动补好 |
| `scripts/install.ps1` | 一键安装（合并词条 + 部署守护 + 挂钩启动器） |
| `docs/MECHANISM.md` | 汉化机制详解 + 怎么自己补词条 |

底层汉化引擎（DOM 翻译器 + 词典）来自开源项目 **[QingniaoDawn/Antigravity-YiJianHanHua](https://github.com/QingniaoDawn/Antigravity-YiJianHanHua)**（词条还整合了另外 4 个社区词库）。
**本仓库不重新分发上游词典**，只以"增量补丁"的形式合并进你本地的 `zh_data.json`——这样上游更新时你不会拿到一份过期的大文件。

---

## 一、汉化是怎么实现的（先看懂这个）

很多人以为汉化是"把 asar 里的英文替换成中文"。**其实不是**——这套工具的机制是**运行时 DOM 翻译器**：

```
IDE 启动
  └─ Electron 主进程（app.asar）
       └─ 注入 engine.js + zh_data.json 到网页界面
            └─ 引擎用 MutationObserver 盯着 DOM
                 ├─ 文本节点 → translateString() → 查词典 → 改写
                 ├─ aria-label / title / placeholder → 同样改写
                 └─ 路由切换、Shadow DOM、焦点恢复都有兜底
```

### 词典结构（`zh_data.json`）

| 字段 | 作用 | 注意 |
|---|---|---|
| `exact` | 整句对照表 | 主力（19k+ 条） |
| `prefix` | 长前缀规则 | **长度必须 ≥16 字符**才生效 |
| `core` | 核心单词 | 用于短文本分词替换 |
| `regex` | **动态模板**（如 `^Explored (\d+) files?$`） | **在词级替换之前跑，吃的是原文** → 动态文案首选 |
| `menuMap` | 原生菜单（File/Edit/View…） | |
| `staticPatches` | 直接改 asar 里 7 个 Electron 主进程文件 | |
| `exempt` | 豁免（别翻） | |

### 引擎**故意不翻**的地方

- `script` / `style` / `textarea` / `input` / `contenteditable`
- 代码块、编辑器（monaco / shiki / prism / codemirror…）
- **用户消息体**、思考链容器（`chat-message-view` / `thought-*` …）
- 斜杠命令菜单（只有 `mentionCategories` 白名单放行）

所以下面这些英文是**设计如此，不是 bug**：

```
项目名 / 会话名        ZcodeX、Helechron、数学答疑
模型名                 Gemini 3.8 Flash
代码块里的命令和工作流   flutter analyze、Check code issues、Build Helechron (Android & iOS)
```

### 官方更新为什么会让汉化"失效"

官方更新会**整体替换 `resources/app.asar`**（里面含注入的引擎和词典）→ 界面立刻回到英文。
本仓库的守护脚本就是盯这个：**比对 `app.asar` 的 SHA256**，变了就重新跑一次 `localize.py apply`。

---

## 二、安装

### 前置

1. 已装 Antigravity IDE
2. 已装上游汉化工具（[下载](https://github.com/QingniaoDawn/Antigravity-YiJianHanHua)），确保能跑通：
   ```powershell
   cd <汉化工具目录>
   python localize.py apply --yes
   python localize.py status     # 应显示「已汉化」
   ```

### 一键安装本仓库的增强

```powershell
# 在本仓库目录执行（PowerShell）
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

`install.ps1` 会做三件事：

1. **合并词条**：把 `patches/zh_data.extra.json` 里的条目合并进汉化工具的 `zh_data.json`（幂等，重复跑不会重复添加）
2. **部署守护**：`ag-han-huajin-guard.ps1` + `ag-han-huajin-watcher.ps1` 放到脚本目录，并注册计划任务 `Antigravity Localization Guard`（每 5 分钟）
3. **挂钩启动器**：如果检测到 `C:\ABP\launch.cmd`（常见的代理插件启动器），在它启动 IDE **之前**插入一次守护调用 → 打开就是中文

然后重新汉化一次让新词条生效：

```powershell
python <汉化工具目录>\localize.py apply --yes
```

---

## 三、以后官方更新了会怎样

```
官方更新落地 → app.asar 被换掉 → 界面变英文
      │
      ├─ IDE 没开着  → 守护脚本发现哈希变了 → 立刻重汉化（约 30 秒）
      └─ IDE 正开着  → 不杀你的 IDE（会丢未保存的工作）→ 布下守望者
                          → 你一关掉 IDE → 守望者几秒内自动补好 → 下次打开是中文
```

> 永不主动杀你正在使用的 IDE —— 最坏情况只是"这次会话是英文，关掉重开就是中文"。

---

## 四、自己补词条（发现还有英文时）

1. **截图定位**：用 CDP `Page.captureScreenshot` 看哪块是英文
   （静态扫 `app.asar` 噪音率 >95%，全是 CSS 类名，不划算；界面文案其实在
   `language_server.exe` 提供的 11MB 单文件 `main.js` 里）
2. **收集可见英文**：CDP 遍历 DOM 收文本节点 + `aria-label`/`title`，排除用户内容
3. **判断是不是漏译**：界面已被引擎处理过，**仍显示英文的才是词典缺的**
4. **加词条** → 编辑 `patches/zh_data.extra.json`：
   - 静态句子 → `exact`
   - 动态模板（`Run X finished`）→ `regex`（用 `$1` 引用分组）
   - 长前缀（≥16 字符）→ `prefix`
5. 重新 `apply --yes`

示例：

```jsonc
{
  "exact":  { "Interface Layout": "界面布局" },
  "prefix": { "Select project, current: ": "选择项目，当前：" },
  "regex":  [
    { "pattern": "^Explored (\\d+) files?$", "replacement": "浏览了 $1 个文件" },
    { "pattern": "^Run (.+) finished$",     "replacement": "运行 $1 完成" }
  ]
}
```

---

## 五、卸载

```powershell
powershell -ExecutionPolicy Bypass -File scripts\uninstall.ps1
```

（只移除本仓库加的东西；上游汉化工具本身不受影响）

---

## 许可

MIT，见 [LICENSE](LICENSE)。

上游汉化工具与词典的版权归其各自作者所有；本仓库只提供增量词条与自动化脚本。
