import { useId } from "react";
import {
  citationAnchorId,
  safeSourceUrl,
  type Citation,
  type VerificationVerdict,
} from "@/lib/citations";

const SUPPORT_BADGES: Record<
  VerificationVerdict["support"],
  { label: string; className: string }
> = {
  full: { label: "Supported", className: "bg-emerald-100 text-emerald-800" },
  partial: { label: "Partial", className: "bg-amber-100 text-amber-800" },
  none: { label: "Unverified", className: "bg-gray-100 text-gray-600" },
};

export function LatestResearchSources({
  citations,
  verification,
  isLoading,
  hasError,
}: {
  citations?: Citation[];
  verification?: VerificationVerdict[];
  isLoading: boolean;
  hasError: boolean;
}) {
  const headingId = useId();
  if (citations === undefined) return null;

  const verdicts = new Map<string, VerificationVerdict>();
  verification?.forEach((verdict) => {
    verdicts.set(verdict.citation_id, verdict);
  });

  const supportCounts = citations.reduce(
    (counts, citation) => {
      counts[verdicts.get(citation.citation_id)?.support ?? "none"] += 1;
      return counts;
    },
    { full: 0, partial: 0, none: 0 },
  );
  const sourceCount = citations.length;
  const summaryParts = [
    `${sourceCount} source${sourceCount === 1 ? "" : "s"}`,
    `${supportCounts.full} supported`,
    `${supportCounts.partial} partial`,
  ];
  if (supportCounts.none > 0) {
    summaryParts.push(`${supportCounts.none} unverified`);
  }
  const hasVerdicts = (verification?.length ?? 0) > 0;

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
        <>
          {hasVerdicts && (
            <p
              role="status"
              className="text-muted-foreground mt-3 text-sm"
            >
              {summaryParts.join(" · ")}
            </p>
          )}
          <ol className="mt-3 flex flex-col gap-3">
            {citations.map((citation, index) => {
              const href =
                citation.source_type === "temporary_research"
                  ? safeSourceUrl(citation.provenance.url)
                  : undefined;
              const verdict = verdicts.get(citation.citation_id);
              const badge = SUPPORT_BADGES[verdict?.support ?? "none"];
              return (
                <li
                  key={index}
                  id={citationAnchorId(citation.citation_id)}
                  data-citation-id={citation.citation_id}
                  className="min-w-0 scroll-mt-4 rounded-md bg-gray-50 p-3 text-sm break-words target:bg-amber-100 target:ring-2 target:ring-amber-300"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium">
                      {citation.citation_id} · {citation.source_label}
                    </p>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}
                    >
                      {badge.label}
                    </span>
                  </div>
                  {verdict?.reason ? (
                    <p className="text-muted-foreground mt-1 text-xs">
                      {verdict.reason}
                    </p>
                  ) : null}
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
                          Section:{" "}
                          {citation.provenance.section_path.join(" › ")}
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
        </>
      )}
    </section>
  );
}
