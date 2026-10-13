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
