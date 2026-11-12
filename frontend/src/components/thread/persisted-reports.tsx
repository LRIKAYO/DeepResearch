import { useEffect, useId, useState } from "react";
import { MarkdownText } from "@/components/thread/markdown-text";
import { LatestResearchSources } from "@/components/thread/sources";
import {
  listSessionReports,
  sessionReportsErrorMessage,
  type StoredReport,
} from "@/lib/backend";

const EXCERPT_LIMIT = 140;

function formatReportTime(createdAt: string): string {
  const date = new Date(createdAt);
  return Number.isNaN(date.valueOf()) ? createdAt : date.toLocaleString();
}

// The excerpt is presentation text: drop block syntax and collapse the rest to
// one line so a Markdown report cannot stretch a compact row.
function reportExcerpt(markdown: string, limit = EXCERPT_LIMIT): string {
  const plain = markdown
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/^\s*\|?[\s:|=_-]+\|?\s*$/gm, " ")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s{0,3}(?:>\s?)+/gm, "")
    .replace(/^\s{0,3}(?:[-*+]|\d+[.)])\s+/gm, "")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/[*~]+/g, "")
    .replace(/\|/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const characters = Array.from(plain);
  if (characters.length <= limit) return plain;

  const truncated = characters.slice(0, limit).join("");
  const lastSpace = truncated.lastIndexOf(" ");
  const cut =
    lastSpace > Math.floor(limit * 0.6)
      ? truncated.slice(0, lastSpace)
      : truncated;
  return `${cut.trimEnd()}…`;
}

export function PersistedReports({
  projectId,
  sessionId,
}: {
  projectId: string;
  sessionId: string;
}) {
  // Remount on pair change: the first render after a new selection must not
  // display rows loaded for the previous session.
  return (
    <PersistedReportsLoader
      key={`${projectId}:${sessionId}`}
      projectId={projectId}
      sessionId={sessionId}
    />
  );
}

function PersistedReportsLoader({
  projectId,
  sessionId,
}: {
  projectId: string;
  sessionId: string;
}) {
  const [reports, setReports] = useState<StoredReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();

  useEffect(() => {
    const controller = new AbortController();
    listSessionReports(projectId, sessionId, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setReports(result);
      })
      .catch((loadError: unknown) => {
        if (!controller.signal.aborted) {
          setError(sessionReportsErrorMessage(loadError));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [projectId, sessionId]);

  return (
    <PersistedReportsView
      reports={reports}
      loading={loading}
      error={error}
    />
  );
}

export function PersistedReportsView({
  reports,
  loading,
  error,
}: {
  reports: StoredReport[];
  loading: boolean;
  error?: string;
}) {
  const headingId = useId();
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!loading && !error && reports.length === 0) return null;

  return (
    <section
      aria-labelledby={headingId}
      className="min-w-0 rounded-lg border p-4"
    >
      <h2
        id={headingId}
        className="font-semibold"
      >
        Saved reports
      </h2>
      {loading ? (
        <p
          role="status"
          className="text-muted-foreground mt-2 text-sm"
        >
          Loading…
        </p>
      ) : null}
      {error ? (
        <p
          role="alert"
          className="text-destructive mt-2 text-sm"
        >
          {error}
        </p>
      ) : null}
      {reports.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-2">
          {reports.map((report) => {
            const expanded = expandedId === report.report_id;
            const panelId = `${headingId}-${report.report_id}`;
            return (
              <li
                key={report.report_id}
                className="rounded-md border text-sm"
              >
                <button
                  type="button"
                  aria-expanded={expanded}
                  aria-controls={expanded ? panelId : undefined}
                  onClick={() =>
                    setExpandedId(expanded ? null : report.report_id)
                  }
                  className="flex w-full min-w-0 flex-col gap-1 rounded-md p-3 text-left hover:bg-gray-50 focus-visible:ring-2 focus-visible:ring-gray-300 focus-visible:outline-none"
                >
                  <span className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                    <time dateTime={report.created_at}>
                      {formatReportTime(report.created_at)}
                    </time>
                    <span>
                      {report.tool_rounds} tool round
                      {report.tool_rounds === 1 ? "" : "s"}
                    </span>
                    <span>
                      {report.citations.length} citation
                      {report.citations.length === 1 ? "" : "s"}
                    </span>
                  </span>
                  <span className="min-w-0 truncate">
                    {reportExcerpt(report.report)}
                  </span>
                </button>
                {expanded ? (
                  <div
                    id={panelId}
                    role="region"
                    aria-label={`Saved report from ${formatReportTime(report.created_at)}`}
                    className="border-t p-3"
                  >
                    <MarkdownText>{report.report}</MarkdownText>
                    <LatestResearchSources
                      citations={report.citations}
                      verification={report.verification}
                      isLoading={false}
                      hasError={false}
                    />
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
