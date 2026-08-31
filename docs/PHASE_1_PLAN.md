# P1-000 — Phase 1 Skeleton Planning

> Phase 1 — ResearchFlow Skeleton Reconstruction  
> Owner: 00-Architect  
> Development Mode: PAIR

## 1. 当前 Repository 事实

截至 P1-000：

- `ResearchFlow/` 是 Git repository，但 `main` 尚无 commit。
- repository 内只有 `docs/source-review/` 下的 Phase 0 文档；全部仍为 untracked files。
- 没有 ResearchFlow 产品代码、`pyproject.toml`、package layout、tests、`langgraph.json` 或根级架构文档。
- `docs/source-review/DECISIONS.md` 与 `TASKS.md` 是空文件，且位于 Phase 0 source-review 范围；项目级 `docs/DECISIONS.md` 尚不存在。
- Workspace 根部的 `compose.yaml` 位于 Git repository 之外，只构建并启动两个 reference snapshot，不能视为 ResearchFlow 实现或部署基线。
- repository 没有 `AGENTS.md`。
- 当前机器有 Python 3.10 / 3.12，但没有 `uv` 命令；repository 本身也尚未声明 Python 版本或 package manager。

因此，Phase 1 不是重构已有 Agent，而是建立第一个由 ResearchFlow 自己拥有的 Python package 和 Graph Contract。

## 2. 问题与约束

目标链路是：

```text
User Query
  → ResearchFlow Graph
  → Researcher
  → Tool
  → Evidence
  → Writer
  → Report
```

第一轮必须同时满足：

- 不复制 Open Deep Research 的主图或节点实现。
- 保留 Phase 0 已确认的顶层 `messages` 集成边界。
- Evidence 是独立 typed state，不从 ToolMessage 文本反向推断。
- 先证明单 Researcher、单 Tool、单 Writer 的数据流；不提前加入 Supervisor 或并行调度。
- 不依赖真实 API key，确保核心 Graph 可以确定性测试。
- 不为未来模块预建无实现的目录或抽象层。

## 3. Agent 代码从哪里开始

### 可选方案

| 方案                                                                  | 判断                                                                                                 |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| 复制 `references/open_deep_research-main` 后删减                      | 拒绝。会把 Supervisor、Compression、配置和 provider 复杂度一起带入，并破坏“从零建立最小骨架”的目标。 |
| 立即建立独立 `agent/` service、独立 deployment 与多 package workspace | 暂缓。当前没有第二个实际 Python deployment，先做服务拆分是推测性设计。                               |
| repository 根级 Python project，采用 `src/researchflow/agent/`        | 推荐。文件最少，模块所有权清晰；以后只有在真实部署或依赖冲突出现时再拆 service。                     |

### 第一轮目标目录

```text
ResearchFlow/
├── pyproject.toml
├── docs/
│   ├── DECISIONS.md
│   └── PHASE_1_PLAN.md
├── src/
│   └── researchflow/
│       ├── __init__.py
│       └── agent/
│           ├── __init__.py
│           ├── state.py
│           └── graph.py
└── tests/
    └── agent/
        └── test_graph.py
```

起点是 `state.py`，不是 prompt、真实搜索 API 或 UI。原因是 Researcher、Tool、Writer 都必须先共享同一条最小数据 Contract，Graph 才能安全连线。

第一轮不创建 `nodes.py`、`tools/` package、Tool Registry 或自定义 interface。节点先留在 `graph.py`；当文件确实出现第二类实现或明显膨胀时再拆。

第一轮也不创建 `langgraph.json`。先用进程内 `graph.invoke()` 证明 Graph State 和 routing；LangGraph Server / Agent Chat UI smoke test 应在本批完成并复核后再决定。

## 4. 第一批任务

依赖关系：

```text
P1-001 Contract + package
        ↓
P1-002 deterministic Graph vertical slice
```

只有两个任务。它们足以回答“ResearchFlow 自己的最小 Graph 是否成立”，再多规划会越过 Rolling Planning Rule。

---

## P1-001 — Agent Package and Minimal State Contract

**Goal**

建立可安装的 ResearchFlow Python package，并定义第一版、明确标记为 provisional 的 Agent State / Evidence Contract。

**Why Now**

当前 repository 没有代码入口。Graph、Tool、Writer 如果在没有共享 state contract 的情况下分别开始，会立刻产生字段命名、reducer 和输出语义冲突。

**Scope**

- 在 repository 根目录建立标准 `pyproject.toml` 与 `src` layout。
- 建立 `researchflow.agent` package。
- 在 `state.py` 定义最小 contract：
  - 外部 conversation input：`messages`；
  - Researcher handoff：`research_query`；
  - Tool output：`evidence`；
  - Writer output：`report`。
- 定义 provisional `Evidence`，第一版只包含足以证明数据流的 `source` 与 `content`。
- 明确 input state、internal state、output state 的边界；只给真正需要合并的字段配置 reducer。
- 创建项目级 `docs/DECISIONS.md`，记录第 5 节列出的决策。
- 声明最小 runtime/test dependencies；不绑定 `uv`、Poetry 等额外工具。

**Out of Scope**

- Graph node 实现和 routing。
- LLM、prompt、真实 Web Search。
- 最终 Evidence Schema、Citation、Evidence ID。
- `langgraph.json`、LangGraph Server、streaming。
- Frontend、Backend、Knowledge package。

**Owner**

01-Agent；00-Architect review State / Evidence Contract。

**Development Mode**

PAIR

**Learning Importance**

HIGH。实现复杂度低，但这是用户第一次为 ResearchFlow 定义 LangGraph State；学习价值不能因代码少而降级。

**Learning Goal**

用户应能解释：

- 为什么 `messages`、`evidence` 和 `report` 是不同生命周期的数据。
- input/internal/output state 分离解决什么问题。
- reducer 何时表示追加，何时应覆盖，以及错误 reducer 如何污染跨 run state。
- 为什么 provisional Evidence 不是最终产品 Schema。

**User Must Complete**

- 用户亲自起草或逐字段确认 State 与 `Evidence` 类型。
- 用户亲自说明每个字段的写入者、读取者和输出边界。
- 用户确认 `docs/DECISIONS.md` 中相关 decision 的 wording。

**AI Assistance Allowed**

- `pyproject.toml`、`__init__.py` 等机械 scaffold。
- import/type error 排查、格式化和 contract review。
- 提醒 reducer 与默认 mutable value 风险，但不替用户决定字段语义。

**Deliverables**

- `pyproject.toml`
- `src/researchflow/__init__.py`
- `src/researchflow/agent/__init__.py`
- `src/researchflow/agent/state.py`
- `docs/DECISIONS.md`

**Acceptance Criteria**

- 标准 editable install 后可 import `researchflow.agent.state`。
- `messages` 是外部聊天兼容边界；`thread_id` 不进入 Graph State。
- `Evidence` 不是 `ToolMessage.content` 的别名，且只有 `source`、`content` 两个 provisional 字段。
- State 明确包含 `research_query`、`evidence`、`report`，没有 project/session/database 字段。
- `docs/DECISIONS.md` 记录 package layout、state/evidence boundary 和 Writer output boundary。
- 没有生成 Graph、server、frontend 或 provider integration。
- 用户能完成 Learning Goal 中的口头 walkthrough；不据此宣称已经掌握 LangGraph。

---

## P1-002 — Single-Researcher Deterministic Graph Slice

**Goal**

用 ResearchFlow 自己的代码实现第一个可测试 Graph：

```text
messages
  → researcher
  → execute_tool
  → evidence
  → writer
  → report + final AIMessage
```

**Why Now**

P1-001 只证明 contract 可以被 import。P1-002 必须证明 state 真正跨节点流动，并验证 Phase 1 主链不依赖 Open Deep Research 的 Supervisor、Compression 或 Writer notes 机制。

**Scope**

- 在 `graph.py` 使用 `StateGraph` 创建单图。
- 实现最小节点：`researcher`、`execute_tool`、`writer`。
- Researcher 最多发起一次 tool call；当前不实现 ReAct 循环。
- 增加一个明确 routing 条件：有 tool call 时进入 `execute_tool`，没有时直接进入 `writer`。
- 通过现有 Runnable/callable 形状注入 researcher model、tool 和 writer；不创建自定义 interface hierarchy。
- Tool node 将结构化结果写入 `evidence`，同时可写标准 ToolMessage 供执行轨迹使用；Writer 只能从 `evidence` 读取研究材料。
- Writer 同时写 `report` 和最终 AIMessage，使 graph output 与 Agent Chat UI 的顶层 `messages` boundary 保持兼容。
- 使用 fake model / fake tool 做无网络、无 API key 的确定性测试。

**Out of Scope**

- 真实 LLM/provider 和 Web Search API。
- 多轮 ReAct、多个 Tool、多 Researcher、Supervisor。
- Compression、Reviewer、Citation formatting。
- LangGraph Server、checkpoint、streaming、Agent Chat UI。
- RAG、Knowledge、FastAPI、数据库、Auth。

**Owner**

01-Agent；00-Architect review routing 与 state ownership。

**Development Mode**

LEARN

**Learning Importance**

HIGH。这是用户第一次实现 ResearchFlow 自有 LangGraph Graph，也是后续所有 Agent 能力的主干。

**Learning Goal**

用户应能独立回答：

1. Graph 为什么存在，为什么当前只有三个节点？
2. 每个节点读取和写入哪些 state？
3. tool call 与 tool execution 为什么是两个动作？
4. Evidence 从哪里产生，Writer 为什么不解析 ToolMessage 文本？
5. routing 条件如何决定 Tool 或 Writer？
6. compiled graph 的入口和最终输出在哪里？
7. 测试失败时应先检查 state update、routing 还是 dependency fake？

**User Must Complete**

- 用户亲自编写 `StateGraph` 节点注册、edges 和 conditional routing。
- 用户亲自实现 Tool result → Evidence state update。
- 用户亲自跟踪一次测试输入从 HumanMessage 到 Report 的完整 state 变化。

**AI Assistance Allowed**

- fake model/tool fixtures、重复测试数据和安装问题。
- 针对用户实现的 code review、错误定位与最小修复建议。
- 格式化、lint 配置和低学习价值 boilerplate。

**Deliverables**

- `src/researchflow/agent/graph.py`
- `tests/agent/test_graph.py`
- 必要时更新 `docs/DECISIONS.md`，但只记录实现中真实出现的新决策。

**Acceptance Criteria**

- `pytest` 在无网络、无 provider key 环境通过。
- happy path 的节点顺序可观察为 `researcher → execute_tool → writer`。
- no-tool path 可直接进入 Writer，并给出明确、可测试的无证据行为。
- fake tool 恰好调用一次，其结构化结果原样进入 `state.evidence`。
- Writer 读取 `evidence` 并同时输出 `report` 与最终 AIMessage。
- 测试能够证明 Writer 不依赖解析 ToolMessage 文本得到 Evidence。
- graph 不 import reference snapshot，也不包含 Supervisor、Compression、RAG 或 server code。
- 用户完成 Learning Goal walkthrough。

**Change Challenge**

完成基本测试后，由用户给 provisional `Evidence` 增加一个可选 `relevance_note`，并亲自更新 fake tool、Writer 输入和断言。目标是验证用户能够修改跨越 State → Tool → Writer 的 Contract，而不只是阅读现成 Graph。

## 5. P1-001 必须写入 `docs/DECISIONS.md` 的设计

以下 decision 必须在写 Graph 前落盘；具体措辞由 P1-001 PAIR 完成：

1. **Python package layout**  
   当前采用根级 `pyproject.toml` + `src/researchflow/agent/`；何时才允许拆成独立 Agent service。
2. **Graph State boundary**  
   `messages` 是外部 conversation contract；`research_query` / `evidence` 是内部研究 state；`report` 是 graph output。
3. **Evidence boundary**  
   第一版 Evidence 仅为 provisional `source + content`；Tool 产生结构化 Evidence，Writer 不解析 ToolMessage 文本。
4. **Writer output boundary**  
   Writer 同时返回 `report` 与最终 AIMessage，以兼容程序调用方和 Agent Chat UI。

暂不记录或决定：

- 最终 Evidence/Citation Schema。
- `evidence_id`、`research_session_id`、`project_id` 等 ID 关系。
- Research Event schema、persistence 与 replay。
- Postgres/checkpoint/deployment topology。

## 6. 第一批 Exit Criteria

### Engineering Exit Criteria

- ResearchFlow 成为可安装的最小 Python project。
- 存在 ResearchFlow 自有、无 upstream 代码复制的 compiled LangGraph。
- 一次确定性调用能完成 User Message → Researcher → Tool → Evidence → Writer → Report。
- 测试无需网络或 secret，并覆盖 happy path 与 no-tool path。
- 项目级决策已进入 `docs/DECISIONS.md`。

### Learning-relevant Findings

批次完成后应检查：

- 用户能否逐节点跟踪 State，而不仅是运行测试。
- 用户能否解释 ToolMessage 与 Evidence 的不同职责。
- 用户能否通过 Change Challenge 修改跨节点 Contract。
- 哪些 LangGraph routing / reducer 问题值得下一批继续亲自实现。

这些只能作为后续验证点，不能在任务开始前宣称用户已经掌握。

## 7. Rolling Planning Stop

P1-001 / P1-002 完成后停止并重新检查 repository、Completion Report 和本批 Exit Criteria。

本文件不规划下一批的真实 Web Tool、LangGraph Server、Agent Chat UI 或其他 Phase 1 任务。如果实现事实使本计划失效，应修改计划，而不是为遵守旧计划强行修改代码。

## 8. 第一批完成复核

P1-001 / P1-002 完成后的实际 Repository 状态：

- 根级 Python package 可以 editable install。
- ResearchFlow 自有 Graph 已实现 `researcher → execute_tool → writer` 与 no-tool 分支。
- Tool 产生结构化 Evidence；Writer 不解析 `ToolMessage.content`。
- Graph 会在新 run 的入口重置 per-run `evidence`，避免 checkpoint thread 沿用旧研究材料。
- 无效 Evidence 会在 Tool execution boundary 被拒绝。
- 确定性测试不需要网络或 secret，并覆盖 happy path、no-tool path、无效 Evidence 和 per-run Evidence reset。
- Repository 仍没有真实 model/search provider、server entry、`langgraph.json` 或 Frontend 实现。

因此第一批 Engineering Exit Criteria 已满足。Learning-relevant Findings 是：用户已经完成一次逐节点 State trace、解释 ToolMessage / Evidence 边界并修改跨节点 Contract；这构成后续学习验证依据，但不据此宣称已经掌握 LangGraph。

## 9. 第二批任务

依赖关系：

```text
P1-003 runtime-ready input / Evidence Contract
        ↓
P1-004 one concrete model + Web tool runtime
        ↓
P1-005 LangGraph Server streaming smoke
```

本批只规划三个任务。完成 P1-005 后再次停止并检查 Repository；不在本文件继续规划 Frontend、Supervisor、RAG 或数据库。

---

## P1-003 — Runtime-ready Input and Evidence Contract

**Goal**

让当前 Graph Contract 能正确承接 Agent Chat UI 的文本 content blocks，并允许一次 Web Search tool call 产生零到多条 provisional Evidence，而不引入真实 provider。

**Why Now**

当前 `researcher` 把 `HumanMessage.content` 直接写入字符串类型的 `research_query`；当输入是 content block list 时会破坏该 Contract。当前 Tool boundary 也只接收单个 Evidence dictionary，而真实搜索通常产生多个独立来源。若先接 provider 或 server，这两类 Contract 问题会与网络和配置故障混在一起。

**Scope**

- 明确 text-only 用户输入边界：支持字符串和包含 text blocks 的 `HumanMessage.content`。
- 将 text blocks 确定性归并为字符串 `research_query`；没有有效文本时明确报错。
- 将 Tool result contract 从单个 Evidence 调整为 `list[Evidence]`。
- 允许空 Evidence list；逐条校验 required / optional 字段。
- `execute_tool` 将 list 原样覆盖写入 `state.evidence`，不再额外包一层 list。
- 更新 deterministic tests 与 D-003，只记录 cardinality / input normalization，不扩展最终 Evidence 字段。

**Out of Scope**

- 图片、音频、文件等多模态输入。
- 真实 LLM、Web Search provider、prompt tuning。
- Citation、Evidence ID、score、metadata 或最终 Evidence Schema。
- 多 Tool、ReAct loop、Supervisor、Compression。
- LangGraph Server、streaming、Frontend 修改。

**Owner**

01-Agent；00-Architect review external input 与 Tool/Evidence Contract。

**Development Mode**

PAIR

**Learning Importance**

HIGH。它把 Phase 0 的 UI `messages` 边界与 Phase 1 的内部研究 State 真正对齐，并改变 Tool → Evidence → Writer 的跨节点 cardinality。

**Learning Goal**

用户应能解释：

- 为什么 `HumanMessage.content` 不保证是字符串，而 `research_query` 应保持 text-only string Contract。
- 输入 normalization 应发生在 Graph 边界，而不是 Writer 或 Frontend 内部。
- 为什么一次 Tool call 与多条 Evidence 并不矛盾。
- 空 list、无效 list item 和 no-tool path 的语义差异。

**User Must Complete**

- 用户确认 text blocks 的拼接与无文本错误语义。
- 用户亲自修改 Tool result → `list[Evidence]` 的 state update。
- 用户亲自跟踪至少两条 Evidence 如何进入 Writer。

**AI Assistance Allowed**

- content block fixture、重复 validation case 和格式化。
- Contract review、错误定位与最小测试建议。
- 不替用户决定最终 Evidence 字段。

**Deliverables**

- `src/researchflow/agent/graph.py`
- `tests/agent/test_graph.py`
- `docs/DECISIONS.md`

**Acceptance Criteria**

- string HumanMessage 与 text-block HumanMessage 都得到确定性的字符串 `research_query`。
- 无有效文本输入在调用 model 前失败。
- Tool 可返回 `[]` 或多条合法 Evidence；Writer 收到相同 list。
- 任一无效 Evidence item 都在 Writer 前失败。
- no-tool path 与“执行 Tool 但结果为空”都有明确测试。
- State schema 不增加 project/thread/session/provider 字段。
- 原有测试继续通过，且不需要网络或 secret。

---

## P1-004 — One Concrete Model and Web Tool Runtime

**Goal**

选择并接入一组 Phase 1 默认 runtime dependencies：一个 chat model provider/model 与一个 Web Search provider，使当前 Graph 能执行一次真实 Query → Search → Evidence → Report。

**Why Now**

P1-003 之后输入与 Evidence cardinality 已稳定到足以承接真实搜索。LangGraph Server 必须加载一个能够自行构造依赖的 graph；当前只有测试注入的 `build_graph(...)`，尚不能作为产品 runtime entry。

**Scope**

- 明确选择一个 chat model provider/model 和一个 Web Search provider。
- Phase 1 允许 Researcher 与 Writer 复用同一 chat model；只有出现真实差异时再拆配置。
- 保留 `build_graph(...)` dependency injection seam 供确定性测试。
- 增加一个最小 runtime graph factory，负责从环境/运行配置构造 concrete model、tool 和 Writer runnable。
- Web Tool 返回 `list[Evidence]`，不把 provider 原始响应或 ToolMessage 文本当正式 Evidence Contract。
- Tool executor 校验模型返回的 tool name 与实际绑定的 concrete tool 一致，不把未知名称路由到唯一工具上执行。
- 凭证只来自环境或 server secret configuration，不进入 Graph State。
- 在 `docs/DECISIONS.md` 记录已选择 provider、配置入口与替换边界。

**Out of Scope**

- 多 provider registry、fallback、自动 model routing。
- 多 Web Tool、MCP、RAG、Hybrid Retrieval。
- retry/circuit breaker、生产限流与成本控制。
- LangGraph Server、Frontend、Auth、Docker。

**Owner**

01-Agent；00-Architect review runtime/config 与 Evidence boundary。

**Development Mode**

LEARN

**Learning Importance**

HIGH。这是 ResearchFlow 第一次真实 Researcher Tool integration；复杂度和学习价值都高。

**Learning Goal**

用户应能解释 model bind、tool call、真实 tool execution、provider response normalization 与 Writer invocation 的完整边界，并知道凭证或 provider 配置为什么不属于 Graph State。

**Deliverables**

- 最小 runtime factory 与 Web Tool 实现。
- provider-specific dependencies 与 `.env.example`。
- 确定性单元测试；具备凭证时增加最小 live smoke 记录。
- `docs/DECISIONS.md` provider/runtime decision。

**Acceptance Criteria**

- 缺少必要配置时给出明确错误，不静默回退 fake provider。
- 确定性测试仍不需要网络或 secret。
- 具备凭证时一次 live query 能产生至少一条合法 Evidence 和最终 Report。
- Provider 原始对象不泄漏到 Agent State 或 Writer Contract。
- 未知 tool name 在实际工具执行前失败。
- 不复制 Open Deep Research provider registry 或工具集合。

---

## P1-005 — LangGraph Server and Streaming Smoke

**Goal**

把 concrete ResearchFlow graph 注册到本地 LangGraph Agent Server，并通过 SDK 验证 assistant selection、thread、checkpoint 与 streaming 的最小端到端链路。

**Why Now**

只有在 P1-004 提供可构造的 runtime graph 后，`langgraph.json` 才能指向真实执行对象。Phase 0 已确认 Agent Chat UI 依赖 LangGraph Server Protocol；本任务先证明 server contract，不同时修改 Frontend。

**Scope**

- 增加最小 `langgraph.json`，只注册一个稳定 graph ID。
- 将 LangGraph CLI 的 in-memory local server 能力放入 development dependency。
- 明确并记录 CLI 的 Python runtime floor；不顺带设计生产 deployment。
- 启动本地 server，验证 `/info`、assistant/graph selection、thread creation 与 streamed run。
- SDK smoke 使用顶层 `messages` 输入，验证 state/message events 最终包含 Report 和 final AIMessage。
- 在同一 thread 上执行第二轮 no-tool 场景，验证旧 Evidence 不进入新 Writer。
- 记录 Agent Chat UI 后续所需 `apiUrl`、`assistantId` 与 `threadId` 配置值。

**Out of Scope**

- ResearchFlow Frontend 修改或 UI 视觉验收。
- Research Event schema、custom stream events 与 replay semantics。
- PostgresSaver、生产持久化、Auth、FastAPI、Docker、部署。

**Owner**

01-Agent；00-Architect review server/assistant/thread Contract；05-Quality review smoke test。

**Development Mode**

PAIR

**Learning Importance**

HIGH。这是用户第一次把自有 Graph 暴露为 LangGraph Server runnable，并验证 Phase 0 的 upstream integration boundary。

**Learning Goal**

用户应能从 SDK request 追踪 `assistantId → threadId → input.messages → Graph State → stream events`，并区分 checkpoint state 与前端当前 `stream.messages`。

**Deliverables**

- `langgraph.json`
- development dependency / environment example 的必要更新。
- 可重复执行的本地 SDK smoke test 或命令记录。
- 必要的 `docs/DECISIONS.md` runtime decision。

**Acceptance Criteria**

- `langgraph dev` 能加载唯一 ResearchFlow graph，无 import/config error。
- SDK 能创建或复用 thread，并按注册 graph ID 发起 streamed run。
- streamed values/messages 最终包含 `report` 与 final AIMessage。
- `thread_id` 不进入 Graph State；同 thread 的 per-run Evidence 不泄漏。
- 不新增 FastAPI adapter、Frontend adapter 或自建 streaming protocol。

## 10. 第二批 Rolling Planning Stop

P1-003 / P1-004 / P1-005 完成后停止。届时根据真实 server smoke 决定下一批是否进入 Agent Chat UI integration；Research Event Contract 仍保持 `ARCHITECTURE DECISION REQUIRED`，本批不顺带设计。
