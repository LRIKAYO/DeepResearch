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

export function safeSourceUrl(value: string): string | undefined {
  try {
    const url = new URL(value);
    if (url.protocol === "https:" || url.protocol === "http:") return url.href;
  } catch {
    // Invalid provenance remains readable text, never an invented destination.
  }
  return undefined;
}
