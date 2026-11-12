import React, {
  createContext,
  useContext,
  ReactNode,
  useState,
  useEffect,
  useMemo,
  useCallback,
} from "react";

import { useStream } from "@langchain/langgraph-sdk/react";
import { type Message } from "@langchain/langgraph-sdk";

import {
  uiMessageReducer,
  isUIMessage,
  isRemoveUIMessage,
  type UIMessage,
  type RemoveUIMessage,
} from "@langchain/langgraph-sdk/react-ui";

import { useQueryState } from "nuqs";

import { LangGraphLogoSVG } from "@/components/icons/langgraph";

import { getApiKey } from "@/lib/api-key";
import { researchFlowUserId } from "@/lib/backend";
import type { Citation, VerificationVerdict } from "@/lib/citations";

import { useProjectSession } from "./ProjectSession";

import { toast } from "sonner";

export type StateType = {
  messages: Message[];
  ui?: UIMessage[];
  citations?: Citation[];
  research_query?: string;
  sub_questions?: string[];
  tool_rounds?: number;
  verification?: VerificationVerdict[];
};

type AgentRunContext = {
  knowledge_scope: {
    user_id: string;
    project_id: string;
  };
  research_session_id: string;
};

const useTypedStream = useStream<
  StateType,
  {
    UpdateType: {
      messages?: Message[] | Message | string;
      ui?: (UIMessage | RemoveUIMessage)[] | UIMessage | RemoveUIMessage;
      context?: Record<string, unknown>;
    };

    CustomEventType: UIMessage | RemoveUIMessage;
    ConfigurableType: AgentRunContext;
  }
>;

type StreamContextType = ReturnType<typeof useTypedStream>;

const StreamContext = createContext<StreamContextType | undefined>(undefined);

async function checkGraphStatus(
  apiUrl: string,
  apiKey: string | null,
  authScheme?: string,
): Promise<boolean> {
  try {
    const headers = new Headers();

    if (apiKey) {
      headers.set("X-Api-Key", apiKey);
    }

    if (authScheme) {
      headers.set("X-Auth-Scheme", authScheme);
    }

    const res = await fetch(`${apiUrl}/info`, {
      headers,
    });

    return res.ok;
  } catch (e) {
    console.error(e);

    return false;
  }
}

const StreamSession = ({
  children,
  apiKey,
  apiUrl,
  assistantId,
  authScheme,
}: {
  children: ReactNode;
  apiKey: string | null;
  apiUrl: string;
  assistantId: string;
  authScheme?: string;
}) => {
  const { selectedProject, selectedSession } = useProjectSession();
  const threadId = selectedSession?.thread_id ?? null;

  const streamValue = useTypedStream({
    apiUrl,

    apiKey: apiKey ?? undefined,

    assistantId,

    ...(authScheme && {
      defaultHeaders: {
        "X-Auth-Scheme": authScheme,
      },
    }),

    threadId,
    fetchStateHistory: true,
    reconnectOnMount: true,

    onCustomEvent: (event, options) => {
      if (isUIMessage(event) || isRemoveUIMessage(event)) {
        options.mutate((prev) => {
          const ui = uiMessageReducer(prev.ui ?? [], event);

          return {
            ...prev,
            ui,
          };
        });
      }
    },
  });

  const submit = useCallback<StreamContextType["submit"]>(
    (values, options) => {
      if (!selectedProject) {
        return Promise.reject(new Error("A selected Project is required."));
      }
      if (!selectedSession) {
        return Promise.reject(
          new Error("A selected research session is required."),
        );
      }
      return streamValue.submit(values, {
        ...options,
        context: {
          knowledge_scope: {
            user_id: researchFlowUserId(),
            project_id: selectedProject.project_id,
          },
          research_session_id: selectedSession.research_session_id,
        },
      });
    },
    [selectedProject, selectedSession, streamValue],
  );

  const scopedStreamValue = useMemo(
    () =>
      Object.create(streamValue, {
        submit: {
          value: submit,
          enumerable: true,
        },
      }) as StreamContextType,
    [streamValue, submit],
  );

  useEffect(() => {
    checkGraphStatus(apiUrl, apiKey, authScheme).then((ok) => {
      if (!ok) {
        toast.error("Failed to connect to LangGraph server", {
          description: () => (
            <p>
              Please ensure your graph is running at <code>{apiUrl}</code> and
              your API key is correctly set (if connecting to a deployed graph).
            </p>
          ),

          duration: 10000,

          richColors: true,

          closeButton: true,
        });
      }
    });
  }, [apiKey, apiUrl, authScheme]);

  return (
    <StreamContext.Provider value={scopedStreamValue}>
      {children}
    </StreamContext.Provider>
  );
};

export const StreamProvider: React.FC<{
  children: ReactNode;
}> = ({ children }) => {
  const envApiUrl = process.env.NEXT_PUBLIC_API_URL;

  const envAssistantId = process.env.NEXT_PUBLIC_ASSISTANT_ID;

  const envAuthScheme = process.env.NEXT_PUBLIC_AUTH_SCHEME;

  const [apiUrl] = useQueryState("apiUrl", {
    defaultValue: envApiUrl || "",
  });

  const [assistantId] = useQueryState("assistantId", {
    defaultValue: envAssistantId || "",
  });

  const [authScheme] = useQueryState("authScheme", {
    defaultValue: envAuthScheme || "",
  });

  // Keep a locally stored API key readable for deployments that require one.
  const [apiKey] = useState(() => {
    const storedKey = getApiKey();

    return storedKey || "";
  });

  const finalApiUrl = apiUrl || envApiUrl;

  const finalAssistantId = assistantId || envAssistantId;

  const finalAuthScheme = authScheme || envAuthScheme || "";

  if (!finalApiUrl || !finalAssistantId) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center p-4">
        <div
          role="alert"
          className="bg-background flex max-w-xl flex-col gap-3 rounded-lg border p-6 shadow-lg"
        >
          <LangGraphLogoSVG className="h-7" />

          <h1 className="text-xl font-semibold tracking-tight">ResearchFlow</h1>

          <h2 className="text-base font-medium">LangGraph is not configured</h2>

          <p className="text-muted-foreground text-sm">
            The LangGraph URL or assistant ID is not configured. Set{" "}
            <code className="bg-muted rounded px-1 py-0.5 font-mono text-xs">
              NEXT_PUBLIC_API_URL
            </code>{" "}
            and{" "}
            <code className="bg-muted rounded px-1 py-0.5 font-mono text-xs">
              NEXT_PUBLIC_ASSISTANT_ID
            </code>{" "}
            in{" "}
            <code className="bg-muted rounded px-1 py-0.5 font-mono text-xs">
              .env.local
            </code>
            , then restart the app.
          </p>
        </div>
      </div>
    );
  }

  return (
    <StreamSession
      apiKey={apiKey}
      apiUrl={finalApiUrl}
      assistantId={finalAssistantId}
      authScheme={finalAuthScheme || undefined}
    >
      {children}
    </StreamSession>
  );
};

export const useStreamContext = (): StreamContextType => {
  const context = useContext(StreamContext);

  if (context === undefined) {
    throw new Error("useStreamContext must be used within a StreamProvider");
  }

  return context;
};

export default StreamContext;
