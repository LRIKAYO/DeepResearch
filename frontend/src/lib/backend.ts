export type Project = {
  project_id: string;
  name: string;
  created_at: string;
};

export type ResearchSession = {
  research_session_id: string;
  project_id: string;
  thread_id: string;
  created_at: string;
};

export class ProductBackendError extends Error {
  constructor(public readonly status: number) {
    super(`Product Backend request failed with status ${status}`);
  }
}

function backendUrl(): string {
  const url = process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, "");
  if (!url) throw new Error("Product Backend URL is not configured");
  return url;
}

export function researchFlowUserId(): string {
  const value = process.env.NEXT_PUBLIC_RESEARCHFLOW_USER_ID?.trim();
  if (!value) throw new Error("ResearchFlow user ID is not configured");
  return value;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("X-ResearchFlow-User-Id", researchFlowUserId());
  const response = await fetch(`${backendUrl()}${path}`, { ...init, headers });
  if (!response.ok) throw new ProductBackendError(response.status);
  return response.json() as Promise<T>;
}

export function listProjects(): Promise<Project[]> {
  return request("/projects");
}

export function createProject(name: string): Promise<Project> {
  return request("/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export function listResearchSessions(
  projectId: string,
): Promise<ResearchSession[]> {
  return request(`/projects/${projectId}/research-sessions`);
}

export function createResearchSession(
  projectId: string,
): Promise<ResearchSession> {
  return request(`/projects/${projectId}/research-sessions`, {
    method: "POST",
  });
}
