import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Button } from "@/components/ui/button";
import {
  documentErrorMessage,
  listProjectDocuments,
  uploadProjectDocument,
  type ProjectDocument,
} from "@/lib/backend";

export function ProjectKnowledge({ projectId }: { projectId?: string }) {
  return (
    <section className="flex flex-col gap-2 border-y py-4">
      <h2 className="px-1 text-sm font-medium">Project Knowledge</h2>
      {projectId ? (
        <KnowledgeDocuments
          key={projectId}
          projectId={projectId}
        />
      ) : (
        <p className="text-muted-foreground px-1 text-sm">
          Select a Project to manage permanent Markdown Knowledge.
        </p>
      )}
    </section>
  );
}

// Keyed by Project: even the first render after selection cannot display old data.
function KnowledgeDocuments({ projectId }: { projectId: string }) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const lifetime = useRef<AbortController | null>(null);
  const [documents, setDocuments] = useState<ProjectDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [listError, setListError] = useState<string>();
  const [uploadError, setUploadError] = useState<string>();
  const [success, setSuccess] = useState<string>();

  const refresh = useCallback(
    (signal: AbortSignal) =>
      listProjectDocuments(projectId, signal)
        .then((result) => {
          if (!signal.aborted) setDocuments(result);
        })
        .catch((error: unknown) => {
          if (!signal.aborted) setListError(documentErrorMessage(error));
        })
        .finally(() => {
          if (!signal.aborted) setLoading(false);
        }),
    [projectId],
  );

  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    void refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const file = inputRef.current?.files?.[0];
    const signal = lifetime.current?.signal;
    if (!signal || signal.aborted || uploading || loading) return;
    setSuccess(undefined);
    setUploadError(undefined);
    const name = file?.name.trim() ?? "";
    if (
      !file ||
      !/\.md$/i.test(name) ||
      name.length > 255 ||
      /[/\\\0]/.test(name)
    ) {
      setUploadError("Choose one Markdown (.md) file with a valid filename.");
      return;
    }
    if (file.size === 0 || file.size > 1_048_576) {
      setUploadError(
        "Choose a non-empty Markdown file no larger than 1,048,576 bytes (1 MiB).",
      );
      return;
    }
    setUploading(true);
    try {
      const document = await uploadProjectDocument(projectId, file, signal);
      if (signal.aborted) return;
      if (inputRef.current) inputRef.current.value = "";
      setSuccess(
        `${document.filename} was saved and indexed for this Project.`,
      );
      // Do not append the POST response: the server owns ordering and membership.
      setLoading(true);
      setListError(undefined);
      await refresh(signal);
    } catch (error) {
      if (!signal.aborted) setUploadError(documentErrorMessage(error));
    } finally {
      if (!signal.aborted) setUploading(false);
    }
  }

  return (
    <>
      <p
        id={`${inputId}-hint`}
        className="text-muted-foreground px-1 text-xs"
      >
        Permanent Project Knowledge, not a chat attachment. One non-empty UTF-8
        .md file, up to 1 MiB. No research session required.
      </p>
      <form
        onSubmit={handleUpload}
        className="flex flex-col gap-2"
      >
        <label
          htmlFor={inputId}
          className="text-sm"
        >
          Markdown document
        </label>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept=".md,text/markdown"
          aria-describedby={`${inputId}-hint`}
          disabled={uploading || loading}
          className="w-full min-w-0 rounded-md border p-2 text-xs file:mr-2 file:font-medium"
        />
        <Button
          type="submit"
          size="sm"
          disabled={uploading || loading}
        >
          {uploading ? "Uploading and indexing…" : "Upload Markdown"}
        </Button>
      </form>
      <div
        role="status"
        className="text-muted-foreground text-sm"
      >
        {uploading ? "Uploading and indexing. Keep this panel open." : success}
      </div>
      {uploadError && (
        <p
          role="alert"
          className="text-destructive text-sm"
        >
          {uploadError}
        </p>
      )}
      <div
        aria-busy={loading}
        className="flex flex-col gap-2"
      >
        {loading ? (
          <p
            role="status"
            className="text-muted-foreground text-sm"
          >
            Loading Documents…
          </p>
        ) : listError ? (
          <p
            role="alert"
            className="text-destructive text-sm"
          >
            {listError}
          </p>
        ) : documents.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            No Markdown Documents in this Project.
          </p>
        ) : (
          <ul
            aria-label="Project Documents"
            className="flex flex-col gap-2"
          >
            {documents.map((document) => (
              <li
                key={document.document_id}
                className="rounded-md border p-2 text-sm"
              >
                <p className="break-words">{document.filename}</p>
                <time
                  dateTime={document.created_at}
                  className="text-muted-foreground text-xs"
                >
                  {new Date(document.created_at).toLocaleString()}
                </time>
              </li>
            ))}
          </ul>
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={loading || uploading}
          onClick={() => {
            const signal = lifetime.current?.signal;
            if (signal && !signal.aborted) {
              setLoading(true);
              setListError(undefined);
              void refresh(signal);
            }
          }}
        >
          {listError ? "Retry Document list" : "Refresh Document list"}
        </Button>
      </div>
    </>
  );
}
