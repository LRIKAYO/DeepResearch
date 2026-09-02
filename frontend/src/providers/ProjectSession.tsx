"use client";
/* eslint-disable react-hooks/set-state-in-effect -- URL navigation is external state and intentionally drives selection resets. */
/* eslint-disable react-refresh/only-export-components -- The provider exports its consumer hook. */

import { validate } from "uuid";
import { useQueryState } from "nuqs";
import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  createProject as postProject,
  createResearchSession as postResearchSession,
  listProjects,
  listResearchSessions,
  type Project,
  ProductBackendError,
  type ResearchSession,
} from "@/lib/backend";

type ProjectSessionContextValue = {
  backendConfigured: boolean;
  projects: Project[];
  researchSessions: ResearchSession[];
  selectedProject: Project | null;
  selectedSession: ResearchSession | null;
  projectsLoading: boolean;
  sessionsLoading: boolean;
  creatingProject: boolean;
  creatingSession: boolean;
  canSubmit: boolean;
  error: string | null;
  selectProject: (projectId: string | null) => Promise<void>;
  selectResearchSession: (researchSessionId: string | null) => Promise<void>;
  createProject: (name: string) => Promise<void>;
  createResearchSession: () => Promise<void>;
};

const ProjectSessionContext = createContext<ProjectSessionContextValue | null>(
  null,
);

function errorMessage(action: string, error: unknown): string {
  if (error instanceof ProductBackendError && error.status === 404) {
    return "The selected Project or research session is no longer available.";
  }
  return `Unable to ${action}. Please try again.`;
}

export function ProjectSessionProvider({ children }: PropsWithChildren) {
  const [projectId, setProjectId] = useQueryState("projectId");
  const [researchSessionId, setResearchSessionId] =
    useQueryState("researchSessionId");
  const [legacyThreadId, setLegacyThreadId] = useQueryState("threadId");
  const [projects, setProjects] = useState<Project[]>([]);
  const [researchSessions, setResearchSessions] = useState<ResearchSession[]>(
    [],
  );
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [loadedProjectId, setLoadedProjectId] = useState<string | null>(null);
  const [creatingProject, setCreatingProject] = useState(false);
  const [creatingSession, setCreatingSession] = useState(false);
  const creatingSessionRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const backendConfigured = Boolean(process.env.NEXT_PUBLIC_BACKEND_URL);

  const clearProjectSelection = useCallback(async () => {
    setResearchSessions([]);
    setLoadedProjectId(null);
    setSessionsLoading(false);
    await Promise.all([setProjectId(null), setResearchSessionId(null)]);
  }, [setProjectId, setResearchSessionId]);

  const selectProject = useCallback(
    async (nextProjectId: string | null) => {
      setError(null);
      setResearchSessions([]);
      setLoadedProjectId(null);
      setSessionsLoading(false);
      await Promise.all([
        setProjectId(nextProjectId),
        setResearchSessionId(null),
      ]);
    },
    [setProjectId, setResearchSessionId],
  );

  const selectResearchSession = useCallback(
    async (nextResearchSessionId: string | null) => {
      setError(null);
      await setResearchSessionId(nextResearchSessionId);
    },
    [setResearchSessionId],
  );

  const clearUnavailableSession = useCallback(async () => {
    setError("The selected research session is unavailable.");
    await setResearchSessionId(null);
  }, [setResearchSessionId]);

  useEffect(() => {
    if (legacyThreadId) void setLegacyThreadId(null);
  }, [legacyThreadId, setLegacyThreadId]);

  useEffect(() => {
    let cancelled = false;

    if (!backendConfigured) {
      return;
    }
    if (projectId && !validate(projectId)) {
      setError("The selected Project is unavailable.");
      void clearProjectSelection();
      return;
    }

    setProjectsLoading(true);
    listProjects()
      .then(async (nextProjects) => {
        if (cancelled) return;
        setProjects(nextProjects);
        if (
          projectId &&
          !nextProjects.some((p) => p.project_id === projectId)
        ) {
          setError("The selected Project is unavailable.");
          await clearProjectSelection();
        }
      })
      .catch((requestError: unknown) => {
        if (!cancelled) setError(errorMessage("load Projects", requestError));
      })
      .finally(() => {
        if (!cancelled) setProjectsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [backendConfigured, clearProjectSelection, projectId]);

  useEffect(() => {
    let cancelled = false;

    if (!backendConfigured || !projectId || !validate(projectId)) return;

    setSessionsLoading(true);
    listResearchSessions(projectId)
      .then((nextSessions) => {
        if (cancelled) return;
        setResearchSessions(nextSessions);
        setLoadedProjectId(projectId);
      })
      .catch(async (requestError: unknown) => {
        if (cancelled) return;
        setError(errorMessage("load research sessions", requestError));
        if (
          requestError instanceof ProductBackendError &&
          requestError.status === 404
        ) {
          await clearProjectSelection();
        }
      })
      .finally(() => {
        if (!cancelled) setSessionsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [backendConfigured, clearProjectSelection, projectId]);

  useEffect(() => {
    if (
      !researchSessionId ||
      loadedProjectId !== projectId ||
      researchSessions.some(
        (session) => session.research_session_id === researchSessionId,
      )
    ) {
      return;
    }
    void clearUnavailableSession();
  }, [
    clearUnavailableSession,
    loadedProjectId,
    projectId,
    researchSessionId,
    researchSessions,
  ]);

  const selectedProject =
    projects.find((project) => project.project_id === projectId) ?? null;
  const visibleResearchSessions = useMemo(
    () => (loadedProjectId === projectId ? researchSessions : []),
    [loadedProjectId, projectId, researchSessions],
  );
  const selectedSession =
    visibleResearchSessions.find(
      (session) => session.research_session_id === researchSessionId,
    ) ?? null;

  const createProject = useCallback(
    async (name: string) => {
      const trimmedName = name.trim();
      if (!trimmedName) {
        setError("Enter a Project name.");
        return;
      }
      if (creatingProject) return;

      setCreatingProject(true);
      setError(null);
      try {
        const project = await postProject(trimmedName);
        setProjects((current) => [project, ...current]);
        await selectProject(project.project_id);
      } catch (requestError) {
        setError(errorMessage("create the Project", requestError));
      } finally {
        setCreatingProject(false);
      }
    },
    [creatingProject, selectProject],
  );

  const createResearchSession = useCallback(async () => {
    if (
      !selectedProject ||
      creatingSession ||
      creatingSessionRef.current ||
      sessionsLoading
    ) {
      return;
    }

    creatingSessionRef.current = true;
    setCreatingSession(true);
    setError(null);
    try {
      const researchSession = await postResearchSession(
        selectedProject.project_id,
      );
      setResearchSessions((current) => [researchSession, ...current]);
      setLoadedProjectId(selectedProject.project_id);
      await selectResearchSession(researchSession.research_session_id);
    } catch (requestError) {
      setError(errorMessage("create the research session", requestError));
    } finally {
      creatingSessionRef.current = false;
      setCreatingSession(false);
    }
  }, [
    creatingSession,
    selectResearchSession,
    selectedProject,
    sessionsLoading,
  ]);

  const value = useMemo(
    () => ({
      backendConfigured,
      projects,
      researchSessions: visibleResearchSessions,
      selectedProject,
      selectedSession,
      projectsLoading,
      sessionsLoading,
      creatingProject,
      creatingSession,
      canSubmit: Boolean(selectedSession) && !creatingSession,
      error: backendConfigured
        ? error
        : "Product Backend URL is not configured.",
      selectProject,
      selectResearchSession,
      createProject,
      createResearchSession,
    }),
    [
      backendConfigured,
      createProject,
      createResearchSession,
      creatingProject,
      creatingSession,
      error,
      projects,
      projectsLoading,
      selectProject,
      selectResearchSession,
      selectedProject,
      selectedSession,
      sessionsLoading,
      visibleResearchSessions,
    ],
  );

  return (
    <ProjectSessionContext.Provider value={value}>
      {children}
    </ProjectSessionContext.Provider>
  );
}

export function useProjectSession(): ProjectSessionContextValue {
  const context = useContext(ProjectSessionContext);
  if (!context) {
    throw new Error(
      "useProjectSession must be used within a ProjectSessionProvider",
    );
  }
  return context;
}
