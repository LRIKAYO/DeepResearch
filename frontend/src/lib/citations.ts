type CitationBase = {
  citation_id: string;
  source_label: string;
  excerpt: string;
};

// Matches agent/citations.py and agent/evidence.py. IDs are run-local ordinals.
export type Citation = CitationBase &
  (
    | {
        source_type: "temporary_research";
        provenance: { url: string; captured_at?: string | null };
      }
    | {
        source_type: "user_upload";
        provenance: {
          document_id: string;
          chunk_id: string;
          filename: string;
          page_number?: number | null;
          section_path?: string[] | null;
        };
      }
  );

// Matches agent/verification.py: verifier verdicts join to Citation by ID.
export type VerificationVerdict = {
  citation_id: string;
  support: "full" | "partial" | "none";
  reason: string;
};

export function safeSourceUrl(value: string): string | undefined {
  try {
    const url = new URL(value);
    if (url.protocol === "https:" || url.protocol === "http:") return url.href;
  } catch {
    // Invalid provenance remains readable text, never an invented destination.
  }
  return undefined;
}

export const CITATION_ANCHOR_PREFIX = "citation-";

/** DOM id of the source row a `[cN]` marker in the report points at. */
export function citationAnchorId(citationId: string): string {
  return `${CITATION_ANCHOR_PREFIX}${citationId}`;
}

const CITATION_MARKER = /\[c([1-9][0-9]*)\]/g;
// Fenced blocks and inline code both quote text verbatim; rewriting a marker
// inside them would corrupt the quoted code.
const CODE_SPAN = /(```[\s\S]*?```|`[^`\n]*`)/g;

/**
 * Turn `[c1]` markers into in-page links to their source row.
 *
 * Fenced code blocks are left alone: a report may quote JSON or regex text that
 * happens to contain the same sequence, and rewriting it would corrupt the code.
 */
export function linkCitationMarkers(markdown: string): string {
  return markdown
    .split(CODE_SPAN)
    .map((part, index) =>
      index % 2 === 1
        ? part
        : part.replace(CITATION_MARKER, (_match, digits: string) => {
            const citationId = `c${digits}`;
            return `[${citationId}](#${citationAnchorId(citationId)})`;
          }),
    )
    .join("");
}
