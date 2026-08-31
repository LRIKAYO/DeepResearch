# Agent Chat UI Source Reconnaissance

> 勘察范围：`references/agent-chat-ui-main`。本文记录当前 pinned snapshot 中 LangGraph Server 数据如何进入前端并渲染为消息、Tool Call 与 Interrupt UI；第 6、7 节中的 ResearchFlow 扩展为建议架构，不是现有后端 Contract。

## 1. Entry Point 与 Client

Agent Chat UI 的页面入口采用 Provider 嵌套结构：

```text
ThreadProvider
└── StreamProvider
    └── ArtifactProvider
        └── Thread
```

其中各层职责不同。

`src/providers/Thread.tsx` 中的 `ThreadProvider` 负责维护历史 thread 列表相关的前端 state，包括 `threads`、`threadsLoading`，并通过 `client.threads.search()` 按 `graph_id` 或 `assistant_id` 查询服务端已有的 threads。

它并不实现完整的 Thread CRUD。目前该 Provider 中没有 thread 创建、删除或重命名逻辑。

新会话开始时，前端可以处于 `threadId = null` 的状态。用户首次调用 `stream.submit()` 时，当前 `useStream` 实现会先调用 `client.threads.create()`，取得 LangGraph Server 返回的 `thread_id`，再用它创建 run；同时通过 `onThreadId` 将该 ID 回传给 UI。`src/providers/Stream.tsx` 中的 `StreamSession` 接收到该 ID 后更新 URL 中的 `threadId`，并重新拉取 thread 列表。

因此可以将两者的职责理解为：

```text
ThreadProvider
    └── 历史 thread 列表读取与本地列表 state

StreamProvider
    └── 当前 thread 的 LangGraph 流式会话
```

LangGraph SDK Client 在 `src/providers/client.ts` 的 `createClient()` 中建立：

```ts
new Client({ apiUrl, apiKey, defaultHeaders })
```

`src/providers/Thread.tsx` 用它调用 `client.threads.search()`；`src/providers/Stream.tsx` 则把 `apiUrl`、`assistantId` 和当前 `threadId` 交给 `useStream` 发起和维护 run 的流式交互。

---

## 2. Assistant / Graph ID 与 Thread

`Assistant / Graph ID` 与 `threadId` 描述的是两个不同维度。

`Assistant / Graph ID` 用于指定执行哪个 Graph，或者指定某个具体 Assistant 配置。Agent Chat UI 同时允许传入 Graph 名称以及 Assistant UUID。

`threadId` 则标识一条服务端持久化的会话执行状态。

它不应被简单理解为“一个承载 messages 数组的容器”。更准确地说，LangGraph 会以 thread 为边界持久化 Graph State，并在执行过程中生成 checkpoints。

Graph State 中可以包含：

```text
messages
ui
以及其他业务 state
```

每个 checkpoint 是某个执行时刻的 state snapshot，因此同一 thread 可以存在历史 checkpoint，并可基于历史 checkpoint 进行 replay / branch。

在 Agent Chat UI 中，前端真正用于渲染当前消息列表的是：

```ts
const messages = stream.messages;
```

即 `useStream` / SDK 根据服务端 state 与流式事件归并后暴露出来的消息视图，而不是前端直接从 `threadId` 中取得一个 messages 数组。

因此关系更准确地表示为：

```text
Assistant / Graph
        │
        ▼
       Run
        │
        ▼
      Thread
        │
        ├── checkpoint 1
        ├── checkpoint 2
        └── checkpoint N
                │
                ▼
          persisted Graph State
                │
                └── messages / ui / ...
                         │
                         ▼
                SDK useStream 归并
                         │
                         ▼
                  stream.messages
```

---

## 3. Streaming 如何进入 Frontend State

`src/providers/Stream.tsx` 中首先声明当前 UI 所理解的 Graph State：

```ts
export type StateType = {
  messages: Message[];
  ui?: UIMessage[];
};
```

随后创建：

```ts
const useTypedStream = useStream<
  StateType,
  {
    UpdateType: { ... };
    CustomEventType: UIMessage | RemoveUIMessage;
  }
>;
```

这里的 `useTypedStream` 本质上是对 `useStream` 做了 TypeScript 类型特化之后得到的类型化别名。

这些泛型用于描述：

```text
StateType
    服务端 Graph State 在前端的结构

UpdateType
    SDK 预期的 state update 数据形状

CustomEventType
    onCustomEvent 能够接收的自定义事件类型
```

它不是运行时向 `useStream` “注入泛型”。

当前 `StreamProvider` 通过：

```ts
const streamValue = useTypedStream({
  apiUrl,
  assistantId,
  threadId,
  fetchStateHistory: true,
  onCustomEvent,
  onThreadId,
});
```

建立当前 thread 的流式上下文。

真正提交消息时，`src/components/thread/index.tsx` 调用：

```ts
stream.submit(...)
```

并指定：

```ts
streamMode: ["values"]
```

这是组件显式请求的 `values` state stream。当前 `useStream` 还会把已被消费的 getter 和已注册的回调所需模式加入实际请求：`Thread` 在渲染时读取 `stream.messages`，因此会追踪 `messages-tuple` 与 `values`；`StreamProvider` 注册了 `onCustomEvent`，因此会追踪 `custom`。所以当前正常交互的有效 stream modes 是这些模式的去重并集，而不应描述成只有 `values`。

SDK 对它们的处理边界不同：`values` 事件更新当前 state snapshot；`messages-tuple` 按 message ID 归并流式 message chunk；`custom` 交给 `onCustomEvent`，当前 UI 只用 `uiMessageReducer()` 归并 Generative UI 事件。

同时提交消息时配置：

```ts
optimisticValues
```

在服务器事件真正返回之前，先将新 HumanMessage 等内容合并进本地 values，从而实现 optimistic UI。

因此整体链路可以理解为：

```text
用户输入
   │
   ▼
stream.submit()
   │
   ├── optimisticValues
   │       │
   │       └── 立即更新本地消息
   │
   ▼
LangGraph Run
   │
   ▼
values stream
   │
   ▼
useStream / SDK reducer
   │
   ▼
stream.values / stream.messages
   │
   ▼
React re-render
```

---

## 4. Message、Tool Call、Interrupt 如何渲染

### Message routing

`src/components/thread/index.tsx` 取得：

```ts
const messages = stream.messages;
```

随后首先过滤 `DO_NOT_RENDER_ID_PREFIX` 消息，再遍历消息。

Human message 进入：

```text
HumanMessage
```

其他消息进入：

```text
AssistantMessage
```

因此 `AssistantMessage` 实际承担 AI message、ToolMessage，以及 interrupt 等相关展示逻辑的进一步路由。

---

### Tool Call

`ai.tsx` 并不是把两类 Tool Call 数据进行“双源合并”。

其处理方式是按优先级选择一种可用表示。

首先检查标准：

```ts
message.tool_calls
```

如果标准 tool call 已经具有可展示的 args，则直接：

```text
ToolCalls(message.tool_calls)
```

否则尝试从 Anthropic streaming content 中解析：

```text
content[type="tool_use"]
        ↓
parseAnthropicStreamedToolCalls()
        ↓
ToolCalls(...)
```

如果标准 `tool_calls` 已存在，但参数暂时为空，则最后仍可以使用标准 tool call 作为兜底展示。

逻辑近似：

```text
standard tool_calls with args
            │
            ├── yes → ToolCalls
            │
            ▼ no
Anthropic tool_use available
            │
            ├── yes → parse → ToolCalls
            │
            ▼ no
standard tool_calls exists
            │
            └── ToolCalls
```

所以它是**顺序选择 fallback source**，而不是把两个来源 merge 成同一组 Tool Calls。

---

### Interrupt

Interrupt 也不是简单根据某个“类型首位”进行判断。

`ai.tsx` 首先通过：

```ts
isAgentInboxInterruptSchema(interrupt)
```

判断 interrupt 是否符合 Agent Inbox schema。

该 schema 对应包含：

```text
action_requests
review_configs
```

的 HITL 数据结构。

如果满足，则交给：

```text
ThreadView
```

处理。

否则，只要存在 interrupt，就进入：

```text
GenericInterruptView
```

作为通用 JSON interrupt 展示。

另外 Interrupt 并不是在任意消息位置都渲染，而需要满足：

```text
isLastMessage
OR
hasNoAIOrToolMessages
```

也就是说，通常只在最后一条相关消息处显示；如果当前根本还没有 AI / Tool message，则允许单独渲染 interrupt。

---

## 5. 当前数据流的边界

### `src/providers/Thread.tsx`

负责历史 thread 列表的读取和列表级前端 state。

主要包括：

```text
threads
threadsLoading
client.threads.search()
```

它不管理完整 Thread CRUD，也不负责当前 thread 内部的实时消息流。

---

### `src/providers/Stream.tsx`

负责建立当前 LangGraph stream context。

当前主要定义：

```text
StateType
UpdateType
CustomEventType
```

并配置：

```text
threadId
fetchStateHistory
onCustomEvent
onThreadId
```

当前的 `onCustomEvent` 只处理：

```text
UIMessage
RemoveUIMessage
```

并通过：

```ts
uiMessageReducer()
```

将 generative UI event 归并到：

```text
values.ui
```

---

### `src/components/thread/index.tsx`

是当前聊天页面的主要交互协调层。

负责：

```text
读取 stream.messages
提交 HumanMessage
stream.submit()
optimisticValues
取消运行
重新生成
checkpoint regenerate
消息列表入口路由
```

它既承担输入交互，也承担消息列表一级 routing，但更细粒度的 AI / Tool / Interrupt 展示继续委托给子组件。

---

### `src/components/thread/messages/ai.tsx`

负责 AI / Tool / Interrupt / Generative UI 的组合与路由。

主要处理：

```text
AI 文本内容
Tool Call source selection
Tool Result routing
Interrupt routing
UIMessage 与 message_id 的关联
BranchSwitcher
CommandBar
```

其中 Generative UI 会从：

```ts
values.ui
```

中查找：

```ts
ui.metadata?.message_id === message.id
```

的 UIMessage，再交给：

```text
LoadExternalComponent
```

加载和渲染。

---

### `src/components/thread/messages/tool-calls.tsx`

应将其定义为：

> **单条 Tool Call / Tool Result 的被动展示层。**

`ToolCalls` 接收外部传入的 `toolCalls` props，并把 tool name、id 和 args 格式化为 UI。

`ToolResult` 接收 `ToolMessage`，并格式化其 content。

该组件本身：

```text
不发起 LangGraph 请求
不维护 run-level streaming state
不负责 Research workflow orchestration
```

但它并不意味着“只能显示执行完成后的静态结果”。

当上游 props 因流状态发生变化时 React 仍会重新渲染该组件；同时 Anthropic streaming `tool_use` 的部分参数可先经过 `parsePartialJson()` 转换，再作为 ToolCalls props 传入。

因此 Research Progress 不应被塞入 `tool-calls.tsx`，根本原因不是“ToolCalls 永远静态”，而是：

> **它的领域职责只是展示单个 Tool Call / Tool Result，而不是管理整个 Research Run 的过程状态。**

---

## 核心数据边界

当前 `messages` 并不只包含自然语言聊天文本。

它至少可能包含：

```text
HumanMessage
AIMessage
ToolMessage
```

因此不能简单描述为“messages 只承载对话内容”。

同样，`ui` 也不能简单描述为“所有非对话动态渲染指令”。

当前 `ui` 使用的是 LangGraph Generative UI 的 `UIMessage` 机制，并且 UIMessage 可以通过：

```text
metadata.message_id
```

与某条 message 建立关联，由 `LoadExternalComponent` 进行渲染。

因此对于 ResearchFlow，更合理的边界约束是：

> **Research Progress 与 Evidence 是 ResearchFlow 的领域状态，不应通过解析 message 文本或某一个 Tool Result 来反推出当前 research execution state。**

Tool Call 代表的是：

```text
某次工具调用
```

而 Research Progress 表达的是：

```text
整个 Research Run 当前推进到了哪里
```

Evidence 表达的是：

```text
Research Run 当前已经收集、筛选、引用了哪些证据
```

三者生命周期与语义不同，因此 Progress / Evidence 应具有独立、类型化的领域 state。

---

## 6. Research Progress / Evidence 应扩展的位置

> 本节是 ResearchFlow 的建议架构，不是当前 Agent Chat UI 已有实现。

ResearchFlow 不应直接把 Research Progress / Evidence 塞进：

```text
message.content
ToolMessage.content
tool-calls.tsx
```

更合理的扩展方向是从 `Stream.tsx` 的 typed stream contract 开始。

### 6.1 扩展 `StateType`

当前：

```ts
type StateType = {
  messages: Message[];
  ui?: UIMessage[];
};
```

ResearchFlow 可以进一步拥有类似：

```text
messages
ui
researchProgress
evidence
```

的领域状态。

概念上例如：

```ts
type StateType = {
  messages: Message[];
  ui?: UIMessage[];

  researchProgress?: ResearchProgress;
  evidence?: Evidence[];
};
```

这样：

```text
messages
```

继续描述 conversational / tool message state；

```text
researchProgress
```

描述 research workflow 当前阶段；

```text
evidence
```

描述已经发现和管理的研究证据。

如果这些信息需要在刷新页面、重新进入 thread 或 checkpoint 恢复后继续存在，则对应字段还应成为后端 LangGraph State 的正式字段，而不仅仅是前端临时 state。

---

### 6.2 扩展 `CustomEventType`

当前：

```ts
CustomEventType: UIMessage | RemoveUIMessage;
```

ResearchFlow 可以考虑增加独立的领域事件，例如概念上的：

```text
ResearchProgressEvent
EvidenceEvent
```

从而形成：

```text
LangGraph execution
      │
      ├── values state
      │
      └── custom events
                │
                ▼
          onCustomEvent
```

Custom Event 更适合表达执行过程中希望低延迟推送到 UI 的增量变化，而持久化领域状态仍应由正式 Graph State 承担。

**ARCHITECTURE DECISION REQUIRED**

Research Progress / Evidence 的正式 event schema、事件粒度、是否使用 snapshot / patch / append 模式，以及服务端 Graph State 与 Custom Event 之间的关系，需要由 Architect 确认 Contract 后再实现。

---

### 6.3 在 `onCustomEvent` 中归并 Research Event

当前逻辑只识别：

```text
UIMessage
RemoveUIMessage
```

然后：

```text
uiMessageReducer
        ↓
values.ui
```

ResearchFlow 可以在此基础上增加领域事件分支，概念上形成：

```text
onCustomEvent(event)
      │
      ├── UIMessage
      │       └── uiMessageReducer → state.ui
      │
      ├── ResearchProgressEvent
      │       └── researchProgressReducer → state.researchProgress
      │
      └── EvidenceEvent
              └── evidenceReducer → state.evidence
```

这样 Streaming transport 层负责接收和归并事件，而具体 React Component 只消费已经结构化的状态。

---

### 6.4 由本地 Research UI 消费

ResearchFlow 应建立自己的本地组件，例如：

```text
ResearchProgress
EvidencePanel
EvidenceList
ResearchStatus
```

这些组件直接消费：

```text
researchProgress
evidence
```

等 typed domain state。

数据流目标应是：

```text
LangGraph Research Nodes
        │
        ├── persistent Graph State
        │      researchProgress / evidence
        │
        └── Custom Events
                    │
                    ▼
              useStream
                    │
                    ▼
              onCustomEvent
                    │
                    ▼
          typed frontend state
              │           │
              ▼           ▼
 ResearchProgress    Evidence UI
```

而不是：

```text
Research Node
      ↓
伪造成 tool result
      ↓
ToolCalls
      ↓
从字符串推断 research progress
```

---

### 6.5 不默认使用 `CustomComponent`

当前 `CustomComponent` 服务于现有 LangGraph Generative UI 机制。

它从：

```text
values.ui
```

中寻找与当前：

```text
message.id
```

关联的 `UIMessage`，再通过：

```text
LoadExternalComponent
```

加载对应 UI。

因此：

```text
CustomComponent
```

适合：

> 某条 message 对应一个由 agent 动态产生的 Generative UI component。

但 Research Progress / Evidence 属于 ResearchFlow 本身的稳定产品 UI 和领域状态，因此不应默认复用 `CustomComponent` 机制。

更合理的默认方向是：

```text
typed Research State
        ↓
本地 ResearchFlow React Component
```

只有未来确认某类 Evidence 或 Research Artifact 本身需要由 Agent 动态决定 UI component 时，才考虑复用 UIMessage / Generative UI 机制。

---

## 7. 对 ResearchFlow 的最终结论

> 本节是 ResearchFlow 的建议架构。

Agent Chat UI 最值得复用的不是某一个展示组件，而是它已经建立好的分层：

```text
Thread identity / persistence
            │
            ▼
       useStream SDK
            │
            ▼
       typed State
            │
       ┌────┴─────┐
       ▼          ▼
   messages    custom events
       │          │
       ▼          ▼
 Message UI    state reducers
                  │
                  ▼
             domain UI
```

ResearchFlow 应保留 Agent Chat UI 已有的：

```text
Thread / checkpoint 模型
useStream 通信层
messages 渲染链路
Tool Call / Tool Result 展示
Interrupt
Generative UI
```

同时在其旁边增加 ResearchFlow 自己的：

```text
ResearchProgress state
Evidence state
Research custom event contract
ResearchProgress UI
Evidence UI
```

核心架构原则是：

> **Conversation State、Tool Execution State 与 Research Domain State 应明确分层。Research Progress / Evidence 不依赖 message 文本或单条 tool result 推断，而应作为独立、类型化、可持久化并可流式更新的领域状态存在。**

Research Event 的正式 schema 与前后端 Contract：

> **ARCHITECTURE DECISION REQUIRED**
