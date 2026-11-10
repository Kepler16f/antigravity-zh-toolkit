<div align="center">

# Antigravity 中文增强工具箱

**让 Antigravity IDE 的中文界面更完整，并在官方更新后自动恢复。**

[使用说明](#快速开始) · [工作原理](#它是怎么工作的) · [自己补词条](#想自己补词条) · [常见问题](#常见问题)

</div>

---

## 这是什么

Antigravity IDE（Google 的 Agentic IDE）自带的汉化方案是**运行时 DOM 翻译器**：把一份词条表注入界面，边跑边把英文替换成中文。这带来两个现实问题：

1. **词条表覆盖不到的地方就还是英文** —— 官方每个新版本都会加新的界面文案（2.30.0 就新加了「界面布局」选项组、语音设置、快捷键页的一批模板文案）。
2. **官方一更新，汉化就整个失效** —— 更新会整体替换 `resources\app.asar`，注入在里面的引擎和词条表一起没了，界面立刻回到英文；官方安装器还会顺手删掉 `app.asar.bak`（用来「还原官方原版」的备份）。

本项目就是来解决这两件事的：

| 交付 | 说明 |
|---|---|
| **增量词条** | 152 条整句 / 5 条前缀 / 34 条正则，覆盖 2.30.0 新增界面、代理动作气泡、快捷键页模板、插件市场动作、无障碍标签等 |
| **更新后自动恢复** | 守护脚本比对 `app.asar` 的哈希，官方更新后自动重新汉化；**IDE 正开着时不会杀它**，而是等它关掉的那几秒内补好 |
| **一键安装** | 合并词条 + 部署守护 + 挂钩启动器（打开 IDE 前先补丁） |
| **机制文档** | 汉化到底怎么实现的、怎么自己补词条（见 [docs/MECHANISM.md](docs/MECHANISM.md)） |

---

## 与上游汉化工具的关系（**不是 fork**）

⚠️ **本项目不是 [QingniaoDawn/Antigravity-YiJianHanHua](https://github.com/QingniaoDawn/Antigravity-YiJianHanHua) 的 fork**，而是它的一个**独立配套增强包**。

原因很实际：上游用的是一份自定义授权声明，其中明确要求「保留本声明、作者署名及仓库地址」，并禁止「去除、涂改本声明或作者署名，或将本工具（整体或部分）冒充为本人原创发布」。所以本仓库：

- **不重新分发**上游的 `localize.py` / `engine.js` / `zh_data.json`，只提供**增量词条**与**自动化脚本**；
- 你需要**先自行安装上游汉化工具**，本项目再往它的词条表里合并增量、并负责「更新后自动恢复」；
- 上游的版权与署名完整保留（见下方「致谢与授权」）。

上游作者：青鸟（QingniaoDawn） · https://github.com/QingniaoDawn/Antigravity-YiJianHanHua

---

## 快速开始

### 前置条件

1. 已安装 Antigravity IDE
2. 已安装上游汉化工具并确认可用：

   ```powershell
   cd <上游汉化工具目录>
   python localize.py apply --yes
   python localize.py status      # 应显示「已汉化」
   ```

   > 需要 Python 3.8+ 与 Node.js 18+（上游工具的硬性要求）。

### 安装本项目

```powershell
git clone https://github.com/Kepler16f/antigravity-zh-toolkit.git
cd antigravity-zh-toolkit
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

`install.ps1` 做三件事：

1. **合并词条** —— 把 `patches/zh_data.extra.json` 合并进上游的 `zh_data.json`
   （用 `scripts/merge_dict.py` 做，**幂等**，重复安装不会重复添加；原文件会先备份成 `zh_data.json.bak-install`）
2. **部署守护** —— 把 `ag-han-huajin-guard.ps1` / `ag-han-huajin-watcher.ps1` 放在脚本目录，并注册计划任务 `Antigravity Localization Guard`（每 5 分钟）
3. **挂钩启动器** —— 如果检测到 `C:\ABP\launch.cmd` 这类启动器，就在它启动 IDE **之前**插入一次守护调用

找不到上游工具目录时可以手动指定：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -ToolDir "<上游汉化工具目录>"
```

### 让新词条生效

```powershell
cd <上游汉化工具目录>
python localize.py apply --yes
```

---

## 之后官方更新了会怎样

```
官方更新落地 → app.asar 被换掉 → 界面变英文
      │
      ├─ IDE 没开着 → 守护脚本发现哈希变了 → 立刻重新汉化（约 30 秒）
      └─ IDE 正开着 → 不杀你的 IDE（会丢未保存的工作）→ 布下守望者
                          → 你一关掉 IDE → 守望者几秒内自动补好
                          → 下次打开就是中文
```

> 设计原则：**永不主动结束你正在使用的 IDE**。最坏情况只是「这次会话是英文，关掉重开就是中文」。

想立刻检查当前状态，可以手动跑一次：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\ag-han-huajin-guard.ps1
```

---

## 它是怎么工作的

```
Antigravity.exe (Electron 主进程)
  └─ 读 resources\app.asar
       ├─ dist/*.js       ← 主进程代码（菜单、托盘、安装向导…）
       └─ 注入引擎到网页界面
            └─ engine.js + zh_data.json
                 └─ MutationObserver 盯着 DOM
                      ├─ 文本节点 → 查词典 → 改写
                      └─ aria-label / title / placeholder → 同样改写
```

词典分五层，匹配顺序是：

```
0. exempt 命中 → 原样返回
1. exact 精确匹配
2. regex 动态规则      ← 原文参与，处理 "Run X finished" 这类模板
3. exact 忽略大小写
4. exact 忽略空白差异
5. prefix 前缀（必须 ≥16 字符才生效）
6. core 核心词分词
```

**引擎故意不翻**的地方：代码块与编辑器、用户消息体、思考链、输入框、斜杠命令菜单。所以下面这些英文是设计如此：

```
项目名 / 会话名        ZcodeX、Helechron、数学答疑
模型名                 Gemini 3.8 Flash
代码块里的命令和工作流   flutter analyze、Check code issues、Build Helechron (Android & iOS)
```

细节（词典字段表、跳过规则清单、更新失效的原理）见 **[docs/MECHANISM.md](docs/MECHANISM.md)**。

---

## 目录结构

```
antigravity-zh-toolkit/
├── README.md
├── LICENSE                    本项目自有代码的许可（MIT）
├── NOTICE                     上游项目与授权声明的说明
├── docs/
│   └── MECHANISM.md           汉化机制详解 + 补词条方法
├── patches/
│   └── zh_data.extra.json     增量词条（exact / prefix / regex）
└── scripts/
    ├── install.ps1            一键安装
    ├── merge_dict.py          词条合并（幂等，大小写敏感）
    ├── ag-han-huajin-guard.ps1    守护：检测到更新就重汉化
    ├── ag-han-huajin-watcher.ps1  退出守望者：IDE 关掉后秒级补好
    └── uninstall.ps1          卸载
```

---

## 想自己补词条

发现界面还有英文时：

1. **截图定位** —— 用 CDP 的 `Page.captureScreenshot` 看是哪一块
   （不要去静态扫 `app.asar`：里面只有主进程代码，界面文案其实由
   `language_server.exe` 提供的 11MB 单文件 `main.js` 承载，静态扫噪音率 >95%，全是 CSS 类名）
2. **收集可见英文** —— CDP 遍历 DOM，取文本节点 + `aria-label` / `title` / `placeholder`，排除用户内容
3. **确认是漏译** —— 界面已经被引擎处理过，**仍显示英文的才是词典缺的**
4. **写进 `patches/zh_data.extra.json`**：

   | 情况 | 放哪 | 例子 |
   |---|---|---|
   | 整句固定 | `exact` | `"Interface Layout": "界面布局"` |
   | 含数字/名字的模板 | `regex` | `^Explored (\d+) files?$` → `浏览了 $1 个文件` |
   | 长前缀（≥16 字符） | `prefix` | `"Select project, current: "` → `"选择项目，当前："` |

5. **重新生效**

   ```powershell
   python scripts\merge_dict.py "<上游汉化工具目录>" patches\zh_data.extra.json
   cd "<上游汉化工具目录>" && python localize.py apply --yes
   ```

详细步骤和踩坑见 [docs/MECHANISM.md](docs/MECHANISM.md)。

---

## 常见问题

**Q：更新后还是英文？**
A：先确认守护脚本在跑（`scripts\guard.log` 有没有记录）、计划任务在不在。
IDE 开着时不会立刻恢复 —— 关掉它，守望者会在几秒内补好。

**Q：安装脚本提示找不到上游汉化工具？**
A：手动指定 `-ToolDir "<工具目录>"`。

**Q：PowerShell 报「字符串缺少终止符」之类的语法错误？**
A：Windows PowerShell 5.1 按 ANSI（GBK）读取 `.ps1`（没有 BOM 时），
脚本里出现中文会直接解析失败。**本项目的脚本一律纯 ASCII**，
中文路径请用通配符查找，不要写死。

**Q：词条合并报「包含重复的键」？**
A：PowerShell 的 `ConvertFrom-Json` 键名不区分大小写，
`"ran commands"` 和 `"Ran commands"` 会撞车。本项目因此用 Python 做合并（`merge_dict.py`）。

**Q：会不会影响上游工具的「一键还原」？**
A：不会。还原用的是上游自己的 `app.asar.bak`，本项目只改词条表并重新 `apply`。
注意官方更新会删掉那个备份 —— 更新后第一次 `apply` 会重新生成它。

---

## 致谢与授权

- 上游汉化工具与词典：**青鸟（QingniaoDawn）** ·
  https://github.com/QingniaoDawn/Antigravity-YiJianHanHua
  —— 引擎、词典与一键汉化流程均出自该项目，本项目在此基础上补充词条并实现「更新后自动恢复」。
  上游版权归其作者所有，本仓库**未**重新分发上游代码与词典，仅提供增量补丁与自动化脚本。
- 本仓库自有代码（增量词条、守护/守望者脚本、安装器、文档）：**MIT**，见 [LICENSE](LICENSE)。
- 本项目与上游项目无隶属关系。

Antigravity 是 Google 的产品；本项目与 Google 无关。
