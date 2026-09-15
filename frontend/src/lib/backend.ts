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

export type ProjectDocument = {
  document_id: string;
  project_id: string;
  filename: string;
  media_type: "text/markdown";
  created_at: string;
};

const documentValidationDetails = new Set([
  "Invalid Markdown filename",
  "Markdown document cannot be empty",
  "Markdown document must be UTF-8",
]);

export class ProductBackendError extends Error {
  constructor(
    public readonly status: number,
    public readonly safeDetail?: string,
  ) {
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
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      body && typeof body === "object" && "detail" in body
        ? body.detail
        : undefined;
    // Only these exact validation strings may reach the UI. Never retain raw errors.
    const safeDetail =
      response.status === 422 &&
      typeof detail === "string" &&
      documentValidationDetails.has(detail)
        ? detail
        : undefined;
    throw new ProductBackendError(response.status, safeDetail);
  }
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

export function listProjectDocuments(
  projectId: string,
  signal?: AbortSignal,
): Promise<ProjectDocument[]> {
  return request(`/projects/${encodeURIComponent(projectId)}/documents`, {
    signal,
  });
}

export function uploadProjectDocument(
  projectId: string,
  file: File,
  signal?: AbortSignal,
): Promise<ProjectDocument> {
  const body = new FormData();
  // Normalize the part MIME without decoding or rewriting the original bytes.
  body.append("file", file.slice(0, file.size, "text/markdown"), file.name);
  return request(`/projects/${encodeURIComponent(projectId)}/documents`, {
    method: "POST",
    body,
    signal,
  });
}

export function documentErrorMessage(error: unknown): string {
  if (!process.env.NEXT_PUBLIC_BACKEND_URL?.trim()) {
    return "Configure NEXT_PUBLIC_BACKEND_URL and restart the frontend.";
  }
  if (!process.env.NEXT_PUBLIC_RESEARCHFLOW_USER_ID?.trim()) {
    return "Configure the local ResearchFlow user ID and restart the frontend.";
  }
  if (error instanceof ProductBackendError) {
    switch (error.status) {
      case 401:
        return "ResearchFlow identity is missing or invalid. Check the local user ID configuration.";
      case 404:
        return "This Project is unavailable. Select an accessible Project and try again.";
      case 413:
        return "Choose a Markdown file no larger than 1,048,576 bytes (1 MiB).";
      case 415:
        return "Only Markdown (.md) files with text/markdown media type are supported.";
      case 422:
        return error.safeDetail
          ? `${error.safeDetail}. Choose a valid non-empty UTF-8 .md file.`
          : "The request was rejected. Check the selected Project and choose a valid non-empty UTF-8 .md file.";
      case 503:
        return "Knowledge indexing is unavailable. Try again later; no Document was saved by this failed upload.";
      default:
        return "The Document request failed. Refresh the list before retrying an upload.";
    }
  }
  return "Cannot reach the Product Backend. Check the connection and refresh the list before retrying an upload.";
}
