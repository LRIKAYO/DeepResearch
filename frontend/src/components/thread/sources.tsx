import { useId } from "react";
import { safeSourceUrl, type Citation } from "@/lib/citations";

export function LatestResearchSources({
  citations,
  isLoading,
  hasError,
}: {
  citations?: Citation[];
  isLoading: boolean;
  hasError: boolean;
}) {
  const headingId = useId();
  if (citations === undefined) return null;

  return (
    <section
      aria-labelledby={headingId}
      className="min-w-0 rounded-lg border p-4"
    >
      <h2
        id={headingId}
        className="font-semibold"
      >
        Latest completed research sources
      </h2>
      <p className="text-muted-foreground mt-1 text-sm">
        Sources from the latest successful research in this session, not
        citations for individual messages or claims. Labels such as c1 apply
        only to that research.
      </p>
      {isLoading ? (
        <p
          role="status"
          className="mt-2 text-sm"
        >
          Research is running. These remain the latest completed sources.
        </p>
      ) : hasError ? (
        <p
          role="status"
          className="mt-2 text-sm"
        >
          The latest request failed. Sources from the last successful research
          remain unchanged.
        </p>
      ) : null}
      {citations.length === 0 ? (
        <p className="text-muted-foreground mt-3 text-sm">
          The latest completed research used no sources.
        </p>
      ) : (
        <ol className="mt-3 flex flex-col gap-3">
          {citations.map((citation, index) => {
            const href =
              citation.source_type === "temporary_research"
                ? safeSourceUrl(citation.provenance.url)
                : undefined;
            return (
              <li
                key={index}
                className="min-w-0 rounded-md bg-gray-50 p-3 text-sm break-words"
              >
                <p className="font-medium">
                  {citation.citation_id} · {citation.source_label}
                </p>
                {citation.source_type === "temporary_research" ? (
                  href ? (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary underline"
                    >
                      {citation.provenance.url}
                      <span className="sr-only"> (opens in a new tab)</span>
                    </a>
                  ) : (
                    <p className="text-muted-foreground">
                      Web source URL unavailable.
                    </p>
                  )
                ) : (
                  <div className="text-muted-foreground">
                    <p>Project document: {citation.provenance.filename}</p>
                    {!!citation.provenance.section_path?.length && (
                      <p>
                        Section: {citation.provenance.section_path.join(" › ")}
                      </p>
                    )}
                    {citation.provenance.page_number != null && (
                      <p>Page: {citation.provenance.page_number}</p>
                    )}
                  </div>
                )}
                <p className="mt-2 whitespace-pre-wrap">{citation.excerpt}</p>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
