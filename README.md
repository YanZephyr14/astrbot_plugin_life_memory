# 拟真生活 (Life Memory for AstrBot)

<p align="center">
  <img src="./logo.png" width="160" height="160" alt="Life Memory Logo" />
</p>

<p align="center">
  <strong>给 AI 角色一个仿真实的生活：每日规划生活起居，记录当天小事与进行中大事，每轮动态注入生活记忆</strong>
</p>

<p align="center">
  <a href="https://github.com/YanZephyr14/astrbot_plugin_life_memory/releases"><img src="https://img.shields.io/badge/version-1.4.0-blue.svg" alt="Version"></a>
  <a href="https://github.com/AstrBotDevs/AstrBot"><img src="https://img.shields.io/badge/AstrBot-%3E%3D4.5.7-green.svg" alt="AstrBot Version"></a>
  <a href="https://github.com/YanZephyr14/astrbot_plugin_life_memory/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-purple.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.12+-orange.svg" alt="Python Version">
</p>

---

> 💡 **致谢与灵感来源**：本项目思路与设计灵感来自社区小肥鱼的 `life-memory` 插件，在此表示诚挚感谢！

## 📖 简介与核心特性

想让人设卡里的“生活线”真正活起来，光写设定是不够的 —— 关键在于拥有**连贯的生活记忆层**：

- **跨轮记忆的盲区**：常规对话历史通常只聚焦于“对用户的印象”，角色缺乏自己独立的生活起居经历；
- **生活线碎片化**：角色昨天说“在等一个快递”，今天就忘了；说“稿子卡住了”，下次提起来又像没发生过；
- **前后连贯的真实感**：通过本插件，角色每天第一次上线都会规划今天大致做什么（结合天气、心境、手头的事、偶尔的突发插曲），并在聊天中自然融入生活背景，前后一致、有日常、有起伏。

### 🌟 亮点特性

1. **事件双轨生命周期**：
   - **当天的小事**（吃了什么、去了哪、买了什么）：记一天（默认 24 小时），再次触碰时刷新续期，隔天自动淡忘；
   - **进行中的事**（在等快递、稿子卡住、跟谁还没和好）：持续跨天保留，直到角色主动用 `life_done` 收尾；附带 7 天长兜底防僵尸挂起。
2. **多角色 (Persona) 独立隔离**：
   - 各个 Persona 拥有独立隔离的生活线与每日规划；
   - 同一角色在所有私聊与群聊中保持完全一致的生活起居状态。
3. **环境与生活多维感知**：
   - 自动划分 8 个自然时段（清晨、早晨、上午、中午、下午、傍晚、晚上、深夜），实时匹配作息；
   - 自动感知中国法定与传统节日，并在规划与对话中烘托节日氛围；
   - 支持穿搭风格与心境状态记录。
4. **性能与 Prompt 缓存最佳实践**：
   - **不污染系统提示词**：采用单轮临时追加（`mark_as_temp()`），不破坏大模型服务端的 Prompt 缓存，避免 Token 费用倍增与高延迟。
5. **WebUI 全景控制台 (Dashboard)**：
   - 内置专属可视化看板，支持多角色切换、人设 Prompt 预览、一键智能起居规划生成与生活事件在线编辑。

---

## 📦 安装与启用

### 方式一：插件市场一键安装（推荐）
在 AstrBot WebUI 的「插件」页面，点击「插件市场」，搜索 `astrbot_plugin_life_memory` 或 `拟真生活`，点击安装即可。

### 方式二：CLI 命令行安装
```bash
uv run astrbot plug install astrbot_plugin_life_memory
```

### 方式三：Git 仓库手动克隆
在 AstrBot 根目录执行：
```bash
git clone https://github.com/YanZephyr14/astrbot_plugin_life_memory.git data/plugins/astrbot_plugin_life_memory
```
安装后重载插件即可直接生效。

---

## 🛠️ 大模型工具 (LLM Tools)

插件向大模型自动注册以下 4 个标准工具（装上即用，模型会根据动态注入的引导自主调用）：

| 工具名称 | 作用 | 参数说明 |
|---|---|---|
| `life_plan` | 规划今天大致做什么 | `day`（今日规划日程）、`twist`（偶发小插曲）、`weather`（天气）、`outfit`（穿搭）、`mood`（心境）等 |
| `life_note` | 记一条自己的生活事件 | `content`（事件内容，60字内）、`ongoing`（是否正在进行中，跨天保留传 `true`） |
| `life_recall` | 回忆生活事件与近期脉络 | 智能调取：进行中的事 + 近期小事 + 前几天历史生活规划 |
| `life_done` | 结束一条进行中的事 | `content`（要结束的事件关键词，自动匹配并收尾） |

---

## 💬 用户与管理员指令

除了供模型自主调用外，用户也可以在聊天中通过指令直接查看和管理生活记忆：

| 指令 | 说明 | 示例 |
|---|---|---|
| `/life status [persona_id]` | 查看当前（或指定）角色的生活记忆状态、时段与今日规划 | `/life status` |
| `/life recall [persona_id]` | 手动回忆生活事件（支持指定角色） | `/life recall cat_girl` |
| `/life plan <规划内容>` | 手动设定今日生活规划 | `/life plan 上午整理书架，下午去猫咖` |
| `/life clear [persona_id]` | 清空当前（或指定）角色的所有生活数据 | `/life clear` |

---

## 🖥️ 可视化控制台 (Dashboard)

在 AstrBot WebUI 中进入插件详情页，打开可视化看板：

- **多角色一览与快捷切换**：自动聚合系统中配置的所有 Persona，点击即可切换并查看各自独立的生活线；
- **角色人设 Prompt 预览**：实时展示当前选中的角色人设设定与字数统计，展开即可查看完整 Prompt；
- **今日生活规划与作息卡片**：展示当前角色的今日安排、穿搭、心境、当前时段与节日状态，支持直接在线编辑；
- **一键智能生活规划**：点击「自动生成今日规划」，调用大模型或自适应拟真生活算法，为角色一键定制符合设定与时段的起居日程；
- **生活事件流在线管理**：按进行中、今日发生、已结束多维度过滤，支持单条标记结束、删除与手动添加生活事件。

---

## ⚙️ 插件配置项

| 配置键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `enabled` | bool | `true` | 总开关（关掉后不再记录/规划，已存数据保留） |
| `inject_guide` | bool | `true` | 是否自动注入使用说明。人设卡已写规则的用户可关闭以节省 Token |
| `small_ttl_hours` | int | `24` | 小事保留时长（小时）。默认 24 小时，之后自动淡忘 |
| `ongoing_ttl_hours` | int | `168` | 进行中大事长兜底时长（小时）。默认 7 天（168 小时） |
| `max_events` | int | `60` | 事件池上限，防止无限膨胀 |
| `storage_scope` | string | `persona` | 存储隔离模式：`persona`（按人格角色设定独立隔离，推荐）或 `global`（全局统合） |
| `enable_holiday` | bool | `true` | 节日感知开关，自动感知中国法定与传统节日并在规划中呈现 |
| `enable_outfit` | bool | `true` | 穿搭感知开关，感知外貌穿着风格 |
| `history_plan_days` | int | `2` | 参考历史规划天数（0~7天），维持生活连续性 |
| `enable_persona_whitelist` | bool | `false` | 是否开启角色白名单 |
| `persona_whitelist` | list | `[]` | 允许启用生活记忆的角色 Persona ID 列表 |
| `session_list_mode` | string | `all` | 会话启用范围：`all`（全部）、`whitelist`（白名单）、`blacklist`（黑名单） |
| `session_list` | list | `[]` | 会话列表（UMO 标识） |

---

## 📝 建议人设片段（可选）

如果你更愿意把用法直接写进**角色的人设卡 / 系统提示**（更贴合角色性格，也可省去每轮注入使用说明的 Token），可以在插件配置里将 **「自动注入使用说明」(`inject_guide`)** 关闭，然后把下面这段加进人设：

```text
【你自己的生活】
· 每天第一次上线，先用 life_plan 记下今天大致做什么（参考天气、心绪、手头的事；偶尔有突发的小事）。
· 你手头常有一两件还没完的事（在等一个快递、写的东西卡住了、跟谁还没和好），会拖好几天。
· ⚠️ 遇到"正在进行、还没结束"的事，当场用 life_note 传 ongoing=true 记下，别等、别只靠脑子记
  ——记了才跨多轮、跨天接得上；结束了用 life_done 收掉。
· 当天的小事（吃了什么、去了哪、买了什么）可以顺手记下（只记一天，隔天自动淡忘），但不必每件都记。
· 想接上"我之前在做什么/在等什么"，用 life_recall 查，别凭空猜。
· 别把机制当话题：不说"我刚记了生活事件"这类话。
```

---

## 🔒 数据安全与隔离

所有数据严格遵循 AstrBot 数据隔离规范，存放于：
```text
data/plugin_data/astrbot_plugin_life_memory/
```
写入采用原子替换与作用域异步锁保护，彻底杜绝数据损坏，插件更新或重新安装时数据绝不丢失。

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 开源。
