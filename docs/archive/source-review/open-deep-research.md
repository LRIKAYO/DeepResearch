# Open Deep Research 源码勘察：核心执行链路

> 范围：`references/open_deep_research-main` 中当前主图的入口、State、Supervisor/Researcher 子图、工具循环、压缩与最终写作。
>
> 本文不讨论 Knowledge/RAG、Evidence Contract、Checkpoint、Streaming、Interrupt、MCP OAuth 或部署配置。

## 1. Entry Point 与输入

`langgraph.json` 注册名为 `"Deep Researcher"`，它指向真正导出的 LangGraph 对象：

```text
src/open_deep_research/deep_researcher.py:deep_researcher
```

`deep_researcher` 由 `deep_researcher_builder.compile()` 得到。图从 `START` 进入第一个实际节点 `clarify_with_user`。

外部请求最少传入 `AgentInputState.messages`：用户会话消息。运行过程会扩展为 `AgentState`，写入 brief、Supervisor 消息、研究 notes 与最终报告等字段。

`clarify_with_user` 有两条路径：

- 需要澄清：追加一条 AI 追问消息并直接到 `END`；本轮不开始研究。
- 不需要澄清，或 `allow_clarification=False`：继续到 `write_research_brief`。

## 2. 一次 Research 的完整数据流

```text
User Query
  │
  ▼
AgentInputState.messages
  │
  ▼
Main graph: clarify_with_user
  ├─ needs clarification ───────────────────────────────► END
  │                                                        （返回追问）
  └─ ready
       ▼
  write_research_brief
       │  写入 research_brief，并初始化 supervisor_messages
       ▼
  research_supervisor（Supervisor 子图）
       │
       ├─ supervisor
       │     │ LLM 生成 think_tool / ConductResearch / ResearchComplete
       │     ▼
       └─ supervisor_tools
             ├─ think_tool：写入反思 ToolMessage，回到 supervisor
             └─ ConductResearch：并发调用一个或多个 Researcher 子图
                   │
                   ▼
              Researcher 子图（每个 research_topic 独立）
                   researcher
                      │ LLM 生成 tool_calls
                      ▼
                   researcher_tools
                      ├─ 执行 web search / think_tool / 其他允许工具
                      ├─ 将结果写为 ToolMessage
                      └─ 回 researcher 继续研究，或转入压缩
                      ▼
                   compress_research
                      │
                      └─ 返回 compressed_research + raw_notes
                            │
                            ▼
                   ConductResearch ToolMessage 回填给 Supervisor
                            │
                            └─ Supervisor 决定继续委派或结束研究
       │
       └─ 结束时从 supervisor_messages 的 ToolMessage 生成 notes
  ▼
Main graph: final_report_generation
  │  使用 research_brief + messages + notes
  ▼
final_report + 最终 AI message
  ▼
END
```

主图负责整个生命周期的编排；Supervisor 负责研究规划、委派和研究是否完成的判断；每个 Researcher 只研究一个独立的 `research_topic`。

## 3. State 与消息边界

| 字段 | 主要写入者 | 主要读取者 | 是否进入 Writer |
|---|---|---|---|
| `messages` | 外部用户、`clarify_with_user`、`final_report_generation` | 澄清、brief 生成、Writer | 是，作为用户会话上下文 |
| `research_brief` | `write_research_brief` | Supervisor、Writer | 是，作为正式研究任务 |
| `supervisor_messages` | `write_research_brief`、`supervisor`、`supervisor_tools` | Supervisor 循环 | 不整体进入；其中 ToolMessage 会在结束时提取为 `notes` |
| `researcher_messages` | `supervisor_tools` 初始化，`researcher`、`researcher_tools` 追加 | Researcher 循环、`compress_research` | 否；子图结束前被整理为 `compressed_research` |
| `compressed_research` | `compress_research` | `supervisor_tools`，随后由 Supervisor 模型阅读 | 间接进入：作为 `ConductResearch` ToolMessage 的内容 |
| `raw_notes` | `compress_research` 生成，`supervisor_tools` 汇总 | 当前仅保留在 State | 否；当前源码不会把它转换为 `notes` |
| `notes` | `supervisor_tools` 结束时调用 `get_notes_from_tool_calls` | `final_report_generation` | 是，作为 `findings` |
| `final_report` | `final_report_generation` | 图调用方 | 最终输出 |

三组消息历史的边界尤其重要：

- `messages` 是用户会话上下文；Writer 会读取它以保持用户语言和需求语境。
- `supervisor_messages` 是 Supervisor 的 system prompt、research brief、模型 tool calls 与工具结果。
- `researcher_messages` 只属于一个 Researcher，包含它自己的 topic、AI tool calls 与 ToolMessage。Researcher 不会自动看到完整主图或其他 Researcher 的消息。

`supervisor_messages`、`raw_notes` 和 `notes` 使用 `override_reducer`：当更新值形如 `{"type": "override", "value": ...}` 时替换，否则列表拼接。其余消息字段使用 LangGraph 的消息/追加 reducer。

## 4. Supervisor / Researcher 与路由

### Supervisor 如何委派

`supervisor()` 只绑定三类工具：`ConductResearch`、`ResearchComplete` 和 `think_tool`；它不绑定 Web Search。

Supervisor 根据 `research_brief` 规划研究方向，并在 AI message 中生成一个或多个 `ConductResearch(research_topic=...)` tool call。每个 `research_topic` 必须是自包含的研究任务，因为下游 Researcher 只接收该 topic 和自身消息。

### Researcher 子图如何启动及并发

`supervisor_tools()` 会筛选最近 AI message 中的 `ConductResearch` calls，并为每一个任务调用：

```python
researcher_subgraph.ainvoke(
    {
        "researcher_messages": [HumanMessage(content=research_topic)],
        "research_topic": research_topic,
    },
    config,
)
```

这些调用通过 `asyncio.gather(...)` 并发执行。一次最多执行 `max_concurrent_research_units` 个；超额任务不会启动，而是收到错误 ToolMessage。

### 两个循环的结束条件

Supervisor 循环是：`supervisor → supervisor_tools → supervisor`。

`supervisor_tools()` 在任一条件成立时结束 Supervisor 子图：

- `research_iterations > max_researcher_iterations`；
- 最近一次 Supervisor AI message 没有 `tool_calls`；
- 最近一次 tool calls 包含 `ResearchComplete`。

Researcher 循环是：`researcher → researcher_tools → researcher`，直到转入 `compress_research`。

转入压缩的条件是：

- 最近 AI message 既没有普通 `tool_calls`，也没有检测到 provider-native Web Search；
- 已执行工具后，`tool_call_iterations >= max_react_tool_calls`；
- 最近 tool calls 包含 `ResearchComplete`。

这两个循环主要通过节点返回的 `Command(goto=..., update=...)` 控制，而不是 `add_conditional_edges`。`Command` 同时表达运行时路由和本节点要写回的 State 更新。

## 5. Tool Calling、think_tool、Compression 与 Writer

### 工具绑定与执行

工具调用分为三个步骤：

1. `get_all_tools(config)` 组装 Researcher 可用工具：固定的 `ResearchComplete`、`think_tool`，再加当前配置的 Web Search 和可选 MCP 工具。
2. `researcher()` 使用 `.bind_tools(tools)` 把工具 schema 暴露给模型。此时模型只能产生 `tool_calls`；工具尚未执行。
3. `researcher_tools()` 读取最近 AI message 的 `tool_calls`，根据名称找到工具并调用 `tool.ainvoke(...)`，再把观测结果写为 `ToolMessage` 并回填到 `researcher_messages`。

Supervisor 的调用由 `supervisor_tools()` 单独处理：`ConductResearch` 会启动 Researcher 子图，而不是直接搜索网页。

### `think_tool` 的实际职责

`think_tool(reflection: str)` 记录模型对当前发现、缺口、证据质量和下一步的反思。

它：

- 不执行 Web Search；
- 不访问外部 API；
- 不负责拆分任务；任务拆分由 Supervisor 生成 `ConductResearch` 完成；
- 不承担持久化 reasoning/audit 数据模型的职责。

它的作用是形成一个明确的 ToolMessage 检查点，让下一轮模型能依据此前反思决定继续搜索、继续委派或结束研究。Supervisor 对它进行特殊处理，直接创建反思 ToolMessage；Researcher 则经由通用工具执行路径调用它。

### `compress_research` 为什么在 Researcher 子图末尾

Researcher 会累积自己的 AI message、ToolMessage、网页搜索结果与反思。若把完整 `researcher_messages` 交给 Supervisor，多个并发 Researcher 的上下文会快速膨胀。

`compress_research` 在子图边界将这些局部记录整理为 `compressed_research`，并生成 `raw_notes`。尽管函数名含有 compress，当前 prompt 要求尽量保留相关信息、来源与引用，而不是只留下极短结论。Supervisor 只接收该整理后的结果，再决定是否需要追加研究。

### Writer 最终消费什么

`final_report_generation()` 构造 Writer prompt 时的核心输入是：

- `research_brief`：最终研究任务；
- `messages`：用户会话上下文；
- `findings`：`"\n".join(notes)`；
- 当前日期。

`notes` 来自 `get_notes_from_tool_calls(supervisor_messages)`，因此当前实现除了 `ConductResearch` 的压缩研究结果，也可能把 `think_tool` 反思或并发溢出的错误信息带入 Writer。

Writer 不直接读取 `researcher_messages`、`supervisor_messages`、`compressed_research` 或 `raw_notes`。它返回 `final_report`，并同时把报告写为最终 AI message，供图调用方或 UI 展示。

## 相关源码

- `references/open_deep_research-main/langgraph.json`
- `references/open_deep_research-main/src/open_deep_research/deep_researcher.py`
- `references/open_deep_research-main/src/open_deep_research/state.py`
- `references/open_deep_research-main/src/open_deep_research/utils.py`
