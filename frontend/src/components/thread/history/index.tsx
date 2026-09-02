import { type FormEvent, useState } from "react";
import { useQueryState, parseAsBoolean } from "nuqs";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { useProjectSession } from "@/providers/ProjectSession";

function sessionLabel(createdAt: string, sessionId: string): string {
  const date = new Date(createdAt);
  const timestamp = Number.isNaN(date.valueOf())
    ? createdAt
    : date.toLocaleString();
  return `${timestamp} · ${sessionId.slice(0, 8)}`;
}

function HistoryLoading() {
  return (
    <div className="flex flex-col gap-2 px-3">
      {Array.from({ length: 5 }).map((_, index) => (
        <Skeleton
          key={index}
          className="h-10 w-full"
        />
      ))}
    </div>
  );
}

function ProductSelection() {
  const [projectName, setProjectName] = useState("");
  const {
    backendConfigured,
    canSubmit,
    createProject,
    createResearchSession,
    creatingProject,
    creatingSession,
    error,
    projects,
    projectsLoading,
    researchSessions,
    selectedProject,
    selectedSession,
    selectProject,
    selectResearchSession,
    sessionsLoading,
  } = useProjectSession();

  const handleCreateProject = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await createProject(projectName);
    setProjectName("");
  };

  if (!backendConfigured) {
    return (
      <p className="text-muted-foreground px-4 text-sm">
        Configure NEXT_PUBLIC_BACKEND_URL to use ResearchFlow.
      </p>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-3 pb-4">
      <form
        className="flex gap-2"
        onSubmit={handleCreateProject}
      >
        <Input
          aria-label="Project name"
          value={projectName}
          onChange={(event) => setProjectName(event.target.value)}
          placeholder="New Project"
          disabled={creatingProject}
        />
        <Button
          type="submit"
          size="sm"
          disabled={creatingProject || !projectName.trim()}
        >
          {creatingProject ? "Creating..." : "Create"}
        </Button>
      </form>

      {error && (
        <p
          role="alert"
          className="text-destructive text-sm"
        >
          {error}
        </p>
      )}

      <section className="flex flex-col gap-2">
        <h2 className="text-muted-foreground px-1 text-sm font-medium">
          Projects
        </h2>
        {projectsLoading ? (
          <HistoryLoading />
        ) : projects.length === 0 ? (
          <p className="text-muted-foreground px-1 text-sm">
            Create a Project to begin.
          </p>
        ) : (
          projects.map((project) => (
            <Button
              key={project.project_id}
              variant="ghost"
              className="w-full justify-start text-left font-normal"
              data-selected={project.project_id === selectedProject?.project_id}
              onClick={() => void selectProject(project.project_id)}
            >
              <span className="truncate">{project.name}</span>
            </Button>
          ))
        )}
      </section>

      <section className="flex min-h-0 flex-col gap-2">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-muted-foreground text-sm font-medium">
            Research sessions
          </h2>
          <Button
            size="sm"
            onClick={() => void createResearchSession()}
            disabled={!selectedProject || sessionsLoading || creatingSession}
          >
            {creatingSession ? "Creating..." : "New research"}
          </Button>
        </div>
        {!selectedProject ? (
          <p className="text-muted-foreground px-1 text-sm">
            Select a Project first.
          </p>
        ) : sessionsLoading ? (
          <HistoryLoading />
        ) : researchSessions.length === 0 ? (
          <p className="text-muted-foreground px-1 text-sm">
            No research sessions yet.
          </p>
        ) : (
          researchSessions.map((session) => (
            <Button
              key={session.research_session_id}
              variant="ghost"
              className="h-auto w-full justify-start py-2 text-left font-normal"
              data-selected={
                session.research_session_id ===
                selectedSession?.research_session_id
              }
              onClick={() =>
                void selectResearchSession(session.research_session_id)
              }
            >
              <span className="truncate">
                {sessionLabel(session.created_at, session.research_session_id)}
              </span>
            </Button>
          ))
        )}
      </section>

      {!canSubmit && selectedProject && !sessionsLoading && (
        <p className="text-muted-foreground px-1 text-sm">
          Create or select a research session before sending a message.
        </p>
      )}
    </div>
  );
}

export default function ThreadHistory() {
  const isLargeScreen = useMediaQuery("(min-width: 1024px)");
  const [chatHistoryOpen, setChatHistoryOpen] = useQueryState(
    "chatHistoryOpen",
    parseAsBoolean.withDefault(false),
  );

  return (
    <>
      <div className="shadow-inner-right hidden h-screen w-[300px] shrink-0 flex-col border-r border-slate-300 lg:flex">
        <div className="flex w-full items-center justify-between px-4 pt-1.5">
          <Button
            className="hover:bg-gray-100"
            variant="ghost"
            onClick={() => setChatHistoryOpen((open) => !open)}
          >
            {chatHistoryOpen ? (
              <PanelRightOpen className="size-5" />
            ) : (
              <PanelRightClose className="size-5" />
            )}
          </Button>
          <h1 className="text-xl font-semibold tracking-tight">Research</h1>
        </div>
        <ProductSelection />
      </div>
      <div className="lg:hidden">
        <Sheet
          open={Boolean(chatHistoryOpen) && !isLargeScreen}
          onOpenChange={(open) => {
            if (!isLargeScreen) void setChatHistoryOpen(open);
          }}
        >
          <SheetContent
            side="left"
            className="flex flex-col lg:hidden"
          >
            <SheetHeader>
              <SheetTitle>Research</SheetTitle>
            </SheetHeader>
            <ProductSelection />
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}
