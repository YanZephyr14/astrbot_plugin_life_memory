# 仿真实生活 (Life Memory) - 待办拆解与开发进度 (backlog.md)

## 待办清单

- [x] **Phase 1: 需求对齐与架构设计**
  - [x] 深度解析原 `life-memory` (JS版本) 的数据模型、算法与提示词注入策略
  - [x] 查阅 AstrBot 官方文档与插件规范，明确生命周期、存储路径及 LLM Tool 签名格式
  - [x] 撰写 `objective.md` 设计目标规范

- [x] **Phase 2: 存储与底层算法模块开发 (`store.py`)**
  - [x] 实现文本归一化 `normalize_text`（去空白、去 Unicode 标点符号与特殊符号、小写转换）
  - [x] 实现事件相似判定 `is_same_event` 与合并去重续期算法 `merge_events`
  - [x] 实现过期淘汰与容量裁剪算法 `prune_events`（小事 24h，大事 168h 兜底，最多 60 条）
  - [x] 实现今日规划管理 `PlanStore` 与事件存储 `EventStore`（原子写入与异常降级）
  - [x] 支持 `session` 与 `global` 两种存储作用域

- [x] **Phase 3: 插件入口与核心功能集成 (`main.py`)**
  - [x] 定义配置 Schema (`_conf_schema.json`) 与元数据 (`metadata.yaml`)
  - [x] 实现继承自 `Star` 的主类及生命周期 `initialize` / `terminate`
  - [x] 实现 4 个 `@filter.llm_tool`：`life_note`, `life_recall`, `life_done`, `life_plan`，规范 Docstring `Args:` 参数定义
  - [x] 实现 `@filter.on_llm_request` 钩子，通过 `TextPart(...).mark_as_temp()` 动态注入临时生活记忆
  - [x] 实现 `@filter.command_group("life")` 管理员/用户指令体系

- [x] **Phase 4: 单元测试与验证**
  - [x] 编写核心算法单测：归一化、相似合并、续期、过期、原子写入
  - [x] 编写 LLM Tool 与 Prompt 注入流程单测
  - [x] 执行全套单测并通过测试 (11/11 passed)

- [x] **Phase 5: 代码质量、版本控制与日志记录**
  - [x] 运行 `ruff check` 与 `ruff format` 格式化代码
  - [x] 编写完整中英用户文档 `README.md`
  - [x] 在插件目录初始化 Git 仓库并完成初始版本 Commit
  - [x] 在根目录 `DEVLOG.md` 追加记录更新详情

- [x] **Phase 6: WebUI 可视化控制台 (Dashboard View) 开发**
  - [x] 查阅 `docs/zh/dev/star/guides/plugin-pages.md` 视图与 API 规范
  - [x] 实现 7 个后端 Web API 接口（概览、事件列表、录入、完成、删除、保存规划、清空）
  - [x] 构建 `views/dashboard/` 前端页面 (`index.html`, `style.css`, `app.js`)
  - [x] 适配暗色与亮色自适应主题，实现指标统计卡片、今日规划卡片与事件流管理
  - [x] 添加 i18n 视图元数据声明 (`.astrbot-plugin/i18n/zh-CN.json`)
  - [x] 编写并运行 Dashboard API 单元测试通过 (12/12 passed)
  - [x] 推送最新功能至 GitHub 远程仓库

- [x] **Phase 7: 动态生活状态融合升级 (吸收 DLS 优势)**
  - [x] 7.1 底层存储与时段算法增强 (`store.py`)：
    - [x] 8 个自然时段区间判定与当前时段解析
    - [x] 多维生活状态注册表 `OPTIONAL_LIFE_FIELDS`（穿搭/心情/地点/节日）
    - [x] 每日规划跨天归档与历史前 1~2 天规划回顾
    - [x] 中国法定与传统节日感知
    - [x] 异步并发锁 `asyncio.Lock` 与熔断计数管理
  - [x] 7.2 插件入口与交互强化 (`main.py`)：
    - [x] 扩展 `life_plan` 工具参数（支持可选穿搭、心情、地点）
    - [x] 升级 `inject_life_context` 提示词注入（自适应当前时段与多维底色）
    - [x] 指令 `/life status` 升级展示时段、穿搭、心境与节日
    - [x] 扩展配置项 `_conf_schema.json`（节日开关、穿搭开关、历史参考天数等）
  - [x] 7.3 WebUI 控制台同步适配：
    - [x] 适配时段徽章、穿搭/心境/地点/节日属性显示与保存编辑
  - [x] 7.4 单元测试扩展与验证：
    - [x] 编写时段算法、状态注册表、归档、并发锁测试
    - [x] 确保全量测试通过 (20/20 passed)
  - [x] 7.5 代码格式化、Git 提交与 DEVLOG 记录

- [x] **Phase 8: 按人格设定隔离与多角色 Dashboard 升级**
  - [x] 8.1 隔离逻辑重构 (`main.py`)：
    - [x] 实现 `get_event_persona_id`：优先从事件上下文中解析当前会话生效的人格 ID，并在 event 中暂存供工具链路复用
    - [x] 将作用域键从会话 UMO 转向 `persona_id`，老会话模式配置平滑兼容
    - [x] 升级 LLM 工具（`life_note`, `life_recall`, `life_done`, `life_plan`）与提示词注入，严格按人格独立隔离
    - [x] 升级指令 `/life status`, `/life recall`, `/life plan`, `/life clear`，显示与操作当前人格
  - [x] 8.2 多人格 Dashboard 后端 Web API 升级 (`main.py`)：
    - [x] 新增/升级 `/dashboard/personas`：列出系统中所有可用人格（含系统 Persona 及本地已存人格）的生活状态统计与设定简介
    - [x] 升级 `/dashboard/overview` 与 `/dashboard/events` 支持基于 `persona_id` 的细粒度过滤与查询
    - [x] 升级事件录入、标记结束、删除、保存规划、清空等接口，面向指定人格生效
  - [x] 8.3 Dashboard 前端视图全面升级 (`views/dashboard/` & `pages/dashboard/`)：
    - [x] 前端界面新增当前人格人设卡片（Persona Info Card），展示角色设定摘要与当前状态
    - [x] 升级人格切换器，支持查看和切换系统中所有人格
    - [x] 增加多角色概览看板模态/抽屉，方便全局掌控所有人格生活状态
    - [x] 保持 `views/` 与 `pages/` 两套静态目录严格一致
  - [x] 8.4 配置与元数据更新 (`_conf_schema.json`, `metadata.yaml`)：
    - [x] 将 `storage_scope` 默认值与说明更新为人格设定隔离
    - [x] 版本提升至 `v1.1.0`
  - [x] 8.5 单元测试编写与验证：
    - [x] 编写同人格跨会话共享测试
    - [x] 编写多人格独立隔离测试
    - [x] 编写多角色 Dashboard API 单元测试
    - [x] 确保所有测试 100% 通过 (24/24 passed)
  - [x] 8.6 代码规范、Git Commit 与 DEVLOG 日志更新

- [x] **Phase 9: 插件专属 Logo 图标与看板视觉品牌升级**
  - [x] 9.1 设计与生成现代 3D 拟真生活专属 App Icon（翻开日记本、成长嫩芽、时钟、日历与书签）
  - [x] 9.2 导出高清标准 `logo.png`（512x512）放置于插件根目录，适配 AstrBot 插件市场规范
  - [x] 9.3 导出 256x256 图标并同步至 `views/dashboard/logo.png` 与 `pages/dashboard/logo.png`
  - [x] 9.4 升级可视化控制台顶部 Header，呈现品牌 Logo 并适配响应式样式
  - [x] 9.5 运行全量单元测试与代码检查，确保 100% 绿色
  - [x] 9.6 提交 Git Commit 并推送至 GitHub 远程仓库，更新 DEVLOG.md

- [x] **Phase 10: 控制台一键开启规划与直接修改插件配置中心 (v1.2.0)**
  - [x] 10.1 后端 Web API 开发：
    - [x] 新增 `POST /{PLUGIN_NAME}/dashboard/plan/auto_generate`：支持指定人格，结合时段、节日、历史规划，优先调用 LLM（或自适应拟真生活降级引擎）一键生成并存入规划
    - [x] 新增 `GET /{PLUGIN_NAME}/dashboard/config`：读取当前生效配置及默认参数
    - [x] 新增 `POST /{PLUGIN_NAME}/dashboard/config/save`：校验参数合法性，更新运行时 `self.config` 并调用 `save_config()` 持久化至磁盘
  - [x] 10.2 前端可视化看板与交互升级 (`views/dashboard/` & `pages/dashboard/`)：
    - [x] 今日规划板块新增「✨ 开始规划」按钮，未规划时提供行内快速规划按键
    - [x] 所有人格全景模态框中，为未规划角色直接提供「✨ 开始规划」单键触发
    - [x] 顶部新增「⚙️ 插件设置」按钮与沉浸式配置中心模态框，支持修改核心功能、隔离模式、节日/穿搭感知与淘汰容量
  - [x] 10.3 单元测试与代码质量验证：
    - [x] 新增自动规划生成与配置修改的完整单测，全量 26 项单元测试全部通过 (26/26 passed)
    - [x] `ruff check` 与 `ruff format` 100% 校验通过
    - [x] 保持双静态目录（`views/` 与 `pages/`）哈希严格一致


