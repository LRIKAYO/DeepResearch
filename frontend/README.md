# ResearchFlow Frontend

ResearchFlow's Next.js client is derived from the workspace snapshot of
[LangChain Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui).
The snapshot has no Git metadata, so this repository does not claim an upstream
commit SHA. Its MIT license is retained in `LICENSE`.

This first integration intentionally reuses the upstream LangGraph Client,
`useStream`, thread/history handling, and standard Message/Tool/Interrupt
rendering. It does not define ResearchFlow Research Progress or Evidence events.

## Local Setup

Start PostgreSQL, the ResearchFlow Product Backend at `http://127.0.0.1:8000`,
and the ResearchFlow LangGraph Server at `http://127.0.0.1:2024`, then:

Install dependencies:

```bash
pnpm install
```

Copy `.env.example` to `.env.local`, then run the app:

```bash
pnpm dev
```

The app will be available at `http://localhost:3000`.

The local connection Contract is:

```text
NEXT_PUBLIC_API_URL=http://127.0.0.1:2024
NEXT_PUBLIC_ASSISTANT_ID=researchflow
NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8000
NEXT_PUBLIC_RESEARCHFLOW_USER_ID=<local opaque UUID>
?projectId=<Product Project UUID>&researchSessionId=<Product Session UUID>
```

`thread_id` is read from the selected Research Session and supplied internally
to `useStream`. It is not a URL or product-navigation value. The browser calls
Product Backend directly for Project and Session control-plane requests; Agent
messages and streams still go directly to LangGraph Agent Server.

Every Frontend `submit` is wrapped centrally and sends the following as SDK Run
context, separate from Graph input and checkpointed State:

```json
{
  "knowledge_scope": {
    "user_id": "<NEXT_PUBLIC_RESEARCHFLOW_USER_ID>",
    "project_id": "<selected Product Project UUID>"
  }
}
```

This local carrier lets the Agent construct its scoped Knowledge Tool, but it
is not authorization. Product Backend still applies the user-and-Project
ownership predicate, and public deployment remains blocked on trusted identity
injection.

`NEXT_PUBLIC_RESEARCHFLOW_USER_ID` is a local-development transport for the
trusted identity header. Because it is exposed to the browser, it is not an
authentication mechanism and must be replaced by a trusted upstream identity
layer before public deployment.

## Basic Integration Smoke

From the repository root, configure the real runtime keys in `.env`, then run:

```powershell
py -m langgraph_cli dev --allow-blocking --no-browser
```

In a second terminal:

```powershell
cd frontend
Copy-Item .env.example .env.local
pnpm install --frozen-lockfile
pnpm dev
```

Open `http://127.0.0.1:3000` and verify:

1. The setup form is skipped and no LangGraph connection error is shown.
2. Create a Project, then select **New research** once.
3. Confirm the URL contains `projectId` and `researchSessionId`, never a
   standalone `threadId`, and message submission remains disabled until the
   Session is created.
4. Submit a request that requires `web_search`; the standard Tool call/result
   trace and final Report render in the selected Session.
5. While a run is active, refresh the page. Confirm the Product Backend first
   restores the Session mapping, then the SDK rejoins the Agent stream.
6. Refresh after the run reaches a terminal status. Confirm the same
   checkpointed conversation returns and the loading indicator does not remain
   active.
7. Switch to another Project and confirm the incompatible Session clears; the
   browser must not request LangGraph `threads.search`.
8. Upload distinct Markdown evidence to two Projects through Product Backend,
   ask the Agent to use `knowledge_search` in each selected Project, and confirm
   each report contains only that Project's evidence. In browser network tools,
   confirm `knowledge_scope` is in the run request's top-level `context`, never
   inside `input` or thread metadata.

This smoke validates the existing messages/thread/stream Contract. The Phase 8
Sources panel below consumes the implemented checkpoint `citations` Contract;
it does not introduce Research Progress events or Evidence replay.

## Project Knowledge and Latest Sources (Phase 8)

Permanent Knowledge is managed in **Project Knowledge** in the existing desktop
sidebar or mobile Research sheet. Select a Project; no Research Session is
required. Use **Markdown document** and **Upload Markdown** to upload one
non-empty UTF-8 `.md` file of at most 1,048,576 bytes. This is separate from the
composer's transient PDF/image attachments.

The browser sends exactly one multipart `file` part, preserving the file bytes
and normalizing its part type to `text/markdown`. Backend `201` means indexing
has completed. The UI then fetches the authoritative Document list, preserving
server order. There is no preview, delete, background job, or progress-percent
feature. Keep the panel open during upload. If the connection or panel closes,
the Backend may still commit the upload: reopen/refresh the list before retrying
to avoid creating a duplicate Document.

The panel maps Document errors to safe, actionable copy. Fix local identity for
`401`, select an accessible Project for `404`, check the file for
`413`/`415`/`422`, and retry indexing later for the documented `503`. Only exact
allowlisted validation details are displayed, never raw response text. A
successful upload followed by a failed list refresh remains a successful upload;
use **Retry Document list**, not a second upload.

After successful research, **Latest completed research sources** appears once
below the conversation. It reads `stream.values.citations`, not Tool text or
Report prose. Web links open their HTTP(S) provenance URL in a new tab; uploaded
Documents show filename and available section/page metadata without a download
link. Order and duplicates are preserved. `c1...` labels are run-local ordinals,
not Product IDs or claim-to-source attribution.

Absent `citations` means no Sources panel; `[]` explicitly means the latest
completed research used no sources. A later running/failed request retains the
last successful inventory as provided by Agent State. No local Sources cache is
added. Reload uses the existing selected Session → `thread_id` → SDK checkpoint
history path. A checkpoint-thread guard prevents another Session's old Sources
from flashing during selection changes.

### Focused module checks

From `frontend`, using the already installed dependencies:

```powershell
pnpm exec esbuild scripts/check-p8.tsx --bundle --platform=node --outfile=.next/p8-check.cjs --jsx=automatic
node .next/p8-check.cjs
pnpm exec tsc --noEmit
pnpm lint
pnpm build
```

The small assertion check covers multipart bytes/MIME/boundary, Document order
and sanitized errors, and Sources rendering/security/lifecycle copy. It does not
replace real-stack browser acceptance. No new E2E fixture framework is added.

### Real-local-stack review checklist

With PostgreSQL/pgvector, Backend, Agent Server, and Frontend running:

1. Select Project A without a Session, upload a valid Markdown file, and check
   that its indexed metadata appears. Switch rapidly between A and B; the list
   must follow the selected Project, including on mobile. With a long sidebar,
   scroll down and click an existing Session while the "Create or select"
   hint is present: the hint must not overlap or intercept the Session button.
2. Check an invalid upload and a failed request: safe error, no phantom entry.
   Retry the list separately from uploading; do not retry an ambiguous upload
   until checking whether it was saved.
3. Create/select a Session and run scoped research using the uploaded content.
   Confirm one Sources panel, correct ordered provenance, and a Report.
4. Reload the same Product URL. Confirm the selected thread's Report and Sources
   recover through SDK history, with no Frontend persistence or source parsing.
5. Start a later run and exercise a controlled Agent failure. The prior Sources
   must remain labelled latest completed; switch Sessions and confirm isolation.

P8-QA-001 owns the full two-Project upload → retrieval → Report/Sources browser
matrix and controlled Agent failure. Module reports must not claim this gate
passed from component checks alone.

## Upstream Feature Reference

The remaining sections describe retained Agent Chat UI capabilities. They are
not all approved ResearchFlow product Contracts.

## Usage

Once the app is running (or if using the deployed site), you'll be prompted to enter:

- **Deployment URL**: The URL of the LangGraph server you want to chat with. This can be a production or development URL.
- **Assistant/Graph ID**: The name of the graph, or ID of the assistant to use when fetching, and submitting runs via the chat interface.
- **LangSmith API Key**: (only required for connecting to deployed LangGraph servers) Your LangSmith API key to use when authenticating requests sent to LangGraph servers.
- **Built with Agent Builder**: Toggle this on for Agent Builder deployments. This automatically sets the auth scheme to `langsmith-api-key`.

After entering these values, click `Continue`. You'll then be redirected to a chat interface where you can start chatting with your LangGraph server.

## Environment Variables

You can bypass the initial setup form by setting the following environment variables:

```bash
NEXT_PUBLIC_API_URL=http://127.0.0.1:2024
NEXT_PUBLIC_ASSISTANT_ID=researchflow
NEXT_PUBLIC_AUTH_SCHEME=
NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8000
NEXT_PUBLIC_RESEARCHFLOW_USER_ID=<local opaque UUID>
```

> [!NOTE]
> If you are connecting to a LangSmith Agent Builder deployment, set `NEXT_PUBLIC_AUTH_SCHEME=langsmith-api-key`.

> [!TIP]
> If you want to connect to a production LangGraph server, read the [Going to Production](#going-to-production) section.

To use these variables:

1. Copy the `.env.example` file to a new file named `.env.local`
2. Fill in the values in the `.env` file
3. Restart the application

When these environment variables are set, the application will use them instead of showing the setup form.

## Hiding Messages in the Chat

You can control the visibility of messages within the Agent Chat UI in two main ways:

**1. Prevent Live Streaming:**

To stop messages from being displayed _as they stream_ from an LLM call, add the `langsmith:nostream` tag to the chat model's configuration. The UI normally uses `on_chat_model_stream` events to render streaming messages; this tag prevents those events from being emitted for the tagged model.

_Python Example:_

```python
from langchain_anthropic import ChatAnthropic

# Add tags via the .with_config method
model = ChatAnthropic().with_config(
    config={"tags": ["langsmith:nostream"]}
)
```

_TypeScript Example:_

```typescript
import { ChatAnthropic } from "@langchain/anthropic";

const model = new ChatAnthropic()
  // Add tags via the .withConfig method
  .withConfig({ tags: ["langsmith:nostream"] });
```

**Note:** Even if streaming is hidden this way, the message will still appear after the LLM call completes if it's saved to the graph's state without further modification.

**2. Hide Messages Permanently:**

To ensure a message is _never_ displayed in the chat UI (neither during streaming nor after being saved to state), prefix its `id` field with `do-not-render-` _before_ adding it to the graph's state, along with adding the `langsmith:do-not-render` tag to the chat model's configuration. The UI explicitly filters out any message whose `id` starts with this prefix.

_Python Example:_

```python
result = model.invoke([messages])
# Prefix the ID before saving to state
result.id = f"do-not-render-{result.id}"
return {"messages": [result]}
```

_TypeScript Example:_

```typescript
const result = await model.invoke([messages]);
// Prefix the ID before saving to state
result.id = `do-not-render-${result.id}`;
return { messages: [result] };
```

This approach guarantees the message remains completely hidden from the user interface.

## Rendering Artifacts

The Agent Chat UI supports rendering artifacts in the chat. Artifacts are rendered in a side panel to the right of the chat. To render an artifact, you can obtain the artifact context from the `thread.meta.artifact` field. Here's a sample utility hook for obtaining the artifact context:

```tsx
export function useArtifact<TContext = Record<string, unknown>>() {
  type Component = (props: {
    children: React.ReactNode;
    title?: React.ReactNode;
  }) => React.ReactNode;

  type Context = TContext | undefined;

  type Bag = {
    open: boolean;
    setOpen: (value: boolean | ((prev: boolean) => boolean)) => void;

    context: Context;
    setContext: (value: Context | ((prev: Context) => Context)) => void;
  };

  const thread = useStreamContext<
    { messages: Message[]; ui: UIMessage[] },
    { MetaType: { artifact: [Component, Bag] } }
  >();

  return thread.meta?.artifact;
}
```

After which you can render additional content using the `Artifact` component from the `useArtifact` hook:

```tsx
import { useArtifact } from "../utils/use-artifact";
import { LoaderIcon } from "lucide-react";

export function Writer(props: {
  title?: string;
  content?: string;
  description?: string;
}) {
  const [Artifact, { open, setOpen }] = useArtifact();

  return (
    <>
      <div
        onClick={() => setOpen(!open)}
        className="cursor-pointer rounded-lg border p-4"
      >
        <p className="font-medium">{props.title}</p>
        <p className="text-sm text-gray-500">{props.description}</p>
      </div>

      <Artifact title={props.title}>
        <p className="whitespace-pre-wrap p-4">{props.content}</p>
      </Artifact>
    </>
  );
}
```

## Going to Production

Once you're ready to go to production, you'll need to update how you connect, and authenticate requests to your deployment. By default, the Agent Chat UI is setup for local development, and connects to your LangGraph server directly from the client. This is not possible if you want to go to production, because it requires every user to have their own LangSmith API key, and set the LangGraph configuration themselves.

### Production Setup

To productionize the Agent Chat UI, you'll need to pick one of two ways to authenticate requests to your LangGraph server. Below, I'll outline the two options:

### Quickstart - API Passthrough

The quickest way to productionize the Agent Chat UI is to use the [API Passthrough](https://github.com/bracesproul/langgraph-nextjs-api-passthrough) package ([NPM link here](https://www.npmjs.com/package/langgraph-nextjs-api-passthrough)). This package provides a simple way to proxy requests to your LangGraph server, and handle authentication for you.

This repository already contains all of the code you need to start using this method. The only configuration you need to do is set the proper environment variables.

```bash
NEXT_PUBLIC_ASSISTANT_ID="agent"
# This should be the deployment URL of your LangGraph server
LANGGRAPH_API_URL="https://my-agent.default.us.langgraph.app"
# This should be the URL of your website + "/api". This is how you connect to the API proxy
NEXT_PUBLIC_API_URL="https://my-website.com/api"
# Your LangSmith API key which is injected into requests inside the API proxy
LANGSMITH_API_KEY="lsv2_..."
```

Let's cover what each of these environment variables does:

- `NEXT_PUBLIC_ASSISTANT_ID`: The ID of the assistant you want to use when fetching, and submitting runs via the chat interface. This still needs the `NEXT_PUBLIC_` prefix, since it's not a secret, and we use it on the client when submitting requests.
- `LANGGRAPH_API_URL`: The URL of your LangGraph server. This should be the production deployment URL.
- `NEXT_PUBLIC_API_URL`: The URL of your website + `/api`. This is how you connect to the API proxy. For the [Agent Chat demo](https://agentchat.vercel.app), this would be set as `https://agentchat.vercel.app/api`. You should set this to whatever your production URL is.
- `LANGSMITH_API_KEY`: Your LangSmith API key to use when authenticating requests sent to LangGraph servers. Once again, do _not_ prefix this with `NEXT_PUBLIC_` since it's a secret, and is only used on the server when the API proxy injects it into the request to your deployed LangGraph server.

For in depth documentation, consult the [LangGraph Next.js API Passthrough](https://www.npmjs.com/package/langgraph-nextjs-api-passthrough) docs.

### Advanced Setup - Custom Authentication

Custom authentication in your LangGraph deployment is an advanced, and more robust way of authenticating requests to your LangGraph server. Using custom authentication, you can allow requests to be made from the client, without the need for a LangSmith API key. Additionally, you can specify custom access controls on requests.

To set this up in your LangGraph deployment, please read the LangGraph custom authentication docs for [Python](https://langchain-ai.github.io/langgraph/tutorials/auth/getting_started/), and [TypeScript here](https://langchain-ai.github.io/langgraphjs/how-tos/auth/custom_auth/).

Once you've set it up on your deployment, you should make the following changes to the Agent Chat UI:

1. Configure any additional API requests to fetch the authentication token from your LangGraph deployment which will be used to authenticate requests from the client.
2. Set the `NEXT_PUBLIC_API_URL` environment variable to your production LangGraph deployment URL.
3. Set the `NEXT_PUBLIC_ASSISTANT_ID` environment variable to the ID of the assistant you want to use when fetching, and submitting runs via the chat interface.
4. Modify the [`useTypedStream`](src/providers/Stream.tsx) (extension of `useStream`) hook to pass your authentication token through headers to the LangGraph server:

```tsx
const streamValue = useTypedStream({
  apiUrl: process.env.NEXT_PUBLIC_API_URL,
  assistantId: process.env.NEXT_PUBLIC_ASSISTANT_ID,
  // ... other fields
  defaultHeaders: {
    Authentication: `Bearer ${addYourTokenHere}`, // this is where you would pass your authentication token
  },
});
```
