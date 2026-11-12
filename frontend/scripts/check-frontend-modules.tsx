// Focused module check: Backend client contract + Sources render contract.
// Not a browser acceptance test. Run with: pnpm check:modules
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import {
  documentErrorMessage,
  listProjectDocuments,
  listSessionReports,
  sessionReportsErrorMessage,
  uploadProjectDocument,
  type StoredReport,
} from "../src/lib/backend";
import {
  citationAnchorId,
  linkCitationMarkers,
  safeSourceUrl,
  type Citation,
} from "../src/lib/citations";
import { LatestResearchSources } from "../src/components/thread/sources";
import { PersistedReportsView } from "../src/components/thread/persisted-reports";

async function main() {
  const originalFetch = globalThis.fetch;
  const originalBackend = process.env.NEXT_PUBLIC_BACKEND_URL;
  const originalUser = process.env.NEXT_PUBLIC_RESEARCHFLOW_USER_ID;
  process.env.NEXT_PUBLIC_BACKEND_URL = "https://backend.invalid";
  process.env.NEXT_PUBLIC_RESEARCHFLOW_USER_ID = "local-test-user";
  try {
    const documents = [
      { document_id: "z", filename: "notes.md" },
      { document_id: "a", filename: "older.md" },
    ];
    const bytes = new Uint8Array([35, 32, 65, 13, 10, 0xc3, 0xa9]);
    for (const type of ["", "application/octet-stream", "text/plain"]) {
      globalThis.fetch = async (url, init) => {
        assert.equal(
          url,
          "https://backend.invalid/projects/project-a/documents",
        );
        assert.equal(init?.method, "POST");
        const headers = new Headers(init.headers);
        assert.equal(headers.get("X-ResearchFlow-User-Id"), "local-test-user");
        assert.equal(headers.has("Content-Type"), false);
        const request = new Request(url, init);
        assert.match(
          request.headers.get("content-type")!,
          /^multipart\/form-data; boundary=/,
        );
        const form = await request.formData();
        assert.deepEqual([...form.keys()], ["file"]);
        const part = form.get("file") as File;
        assert.equal(part.type, "text/markdown");
        assert.equal(part.name, "notes.md");
        assert.deepEqual(new Uint8Array(await part.arrayBuffer()), bytes);
        return Response.json(documents[0], { status: 201 });
      };
      await uploadProjectDocument(
        "project-a",
        new File([bytes], "notes.md", { type }),
      );
    }
    globalThis.fetch = async () => Response.json(documents);
    assert.deepEqual(await listProjectDocuments("project-a"), documents);

    for (const status of [401, 404, 413, 415, 422, 503, 500]) {
      globalThis.fetch = async () =>
        Response.json({ detail: "SECRET provider traceback" }, { status });
      await assert.rejects(
        listProjectDocuments("project-a"),
        (error: unknown) => {
          const copy = documentErrorMessage(error);
          assert.ok(copy.length > 20);
          assert.ok(!copy.includes("SECRET"));
          return true;
        },
      );
    }
    globalThis.fetch = async () =>
      Response.json(
        { detail: "Markdown document must be UTF-8" },
        { status: 422 },
      );
    await assert.rejects(
      listProjectDocuments("project-a"),
      (error: unknown) => {
        assert.match(documentErrorMessage(error), /must be UTF-8/);
        return true;
      },
    );
    assert.match(
      documentErrorMessage(new TypeError("SECRET connection")),
      /Check the connection/,
    );

    const storedReport: StoredReport = {
      report_id: "11111111-1111-4111-8111-111111111111",
      research_session_id: "22222222-2222-4222-8222-222222222222",
      report: "# Weekly update\n\n**Revenue** grew.",
      citations: [],
      verification: [],
      tool_rounds: 2,
      created_at: "2026-11-11T15:04:05+00:00",
    };
    let reportUrl: RequestInfo | URL | undefined;
    let reportSignal: RequestInit["signal"];
    globalThis.fetch = async (url, init) => {
      reportUrl = url;
      reportSignal = init?.signal;
      const headers = new Headers(init?.headers);
      assert.equal(headers.get("X-ResearchFlow-User-Id"), "local-test-user");
      assert.equal(init?.method, undefined);
      assert.equal(init?.body, undefined);
      return Response.json([storedReport]);
    };
    const reportController = new AbortController();
    const listedReports = await listSessionReports(
      "project a/1",
      "session?x",
      reportController.signal,
    );
    assert.equal(
      reportUrl,
      "https://backend.invalid/projects/project%20a%2F1/research-sessions/session%3Fx/reports",
    );
    assert.equal(reportSignal, reportController.signal);
    assert.deepEqual(listedReports, [storedReport]);

    for (const status of [401, 404, 500]) {
      globalThis.fetch = async () =>
        Response.json({ detail: "SECRET provider traceback" }, { status });
      await assert.rejects(
        listSessionReports("project-a", "session-a"),
        (error: unknown) => {
          const copy = sessionReportsErrorMessage(error);
          assert.ok(copy.length > 20);
          assert.ok(!copy.includes("SECRET"));
          assert.ok(!/status \d{3}/i.test(copy));
          return true;
        },
      );
    }
    assert.match(
      sessionReportsErrorMessage(new TypeError("SECRET connection")),
      /Check the connection/,
    );
    delete process.env.NEXT_PUBLIC_RESEARCHFLOW_USER_ID;
    assert.match(
      documentErrorMessage(new Error("SECRET")),
      /Configure the local ResearchFlow user ID/,
    );

    const web: Citation = {
      citation_id: "c1",
      source_type: "temporary_research",
      source_label: "Web source",
      excerpt: "<script>plain text</script>",
      provenance: { url: "https://example.org/source" },
    };
    const upload: Citation = {
      citation_id: "c2",
      source_type: "user_upload",
      source_label: "Uploaded source",
      excerpt: "Evidence",
      provenance: {
        document_id: "d",
        chunk_id: "k",
        filename: "notes.md",
        page_number: 2,
        section_path: ["Policy", "Scope"],
      },
    };
    const render = (
      citations?: Citation[],
      isLoading = false,
      hasError = false,
    ) =>
      renderToStaticMarkup(
        <LatestResearchSources
          citations={citations}
          isLoading={isLoading}
          hasError={hasError}
        />,
      );
    assert.equal(render(), "");
    assert.match(render([]), /used no sources/);
    const sources = [web, upload, web];
    const before = JSON.stringify(sources);
    const html = render(sources);
    assert.equal((html.match(/<li /g) ?? []).length, 3);
    assert.equal((html.match(/<a /g) ?? []).length, 2);
    assert.ok(html.indexOf("Web source") < html.indexOf("Uploaded source"));
    assert.ok(html.lastIndexOf("Web source") > html.indexOf("Uploaded source"));
    assert.match(html, /rel="noopener noreferrer"/);
    assert.match(html, /target="_blank"/);
    assert.match(html, /Policy › Scope/);
    assert.match(html, /Page: 2/);
    assert.ok(!html.includes("<script>"));
    assert.match(render(sources, true), /Research is running/);
    assert.match(
      render(sources, false, true),
      /last successful research remain unchanged/,
    );
    assert.equal(JSON.stringify(sources), before);
    for (const url of [
      "javascript:alert(1)",
      "data:text/html,bad",
      "/relative",
      "invalid",
    ]) {
      assert.equal(safeSourceUrl(url), undefined);
      assert.ok(!render([{ ...web, provenance: { url } }]).includes("<a "));
    }
    assert.equal(
      safeSourceUrl("http://example.org/path"),
      "http://example.org/path",
    );
    // Citation markers become in-page links to their source row.
    assert.equal(citationAnchorId("c1"), "citation-c1");
    assert.equal(
      linkCitationMarkers("defaults to 3 [c1] and [c2]."),
      "defaults to 3 [c1](#citation-c1) and [c2](#citation-c2).",
    );
    assert.equal(
      linkCitationMarkers("```js\nconst pattern = /[c1]/;\n```"),
      "```js\nconst pattern = /[c1]/;\n```",
    );
    assert.equal(
      linkCitationMarkers("[未证实] no source"),
      "[未证实] no source",
    );
    assert.equal(
      linkCitationMarkers("an inline `[c1]` stays literal"),
      "an inline `[c1]` stays literal",
    );
    assert.match(html, /id="citation-c1"/);
    assert.match(html, /data-citation-id="c1"/);

    // Persisted Reports: no rows and no error means no section at all.
    assert.equal(
      renderToStaticMarkup(
        <PersistedReportsView
          reports={[]}
          loading={false}
        />,
      ),
      "",
    );
    const loadingReports = renderToStaticMarkup(
      <PersistedReportsView
        reports={[]}
        loading
      />,
    );
    assert.match(loadingReports, /Saved reports/);
    assert.match(loadingReports, /Loading…/);
    const failedReports = renderToStaticMarkup(
      <PersistedReportsView
        reports={[]}
        loading={false}
        error="Saved reports are unavailable for this research session."
      />,
    );
    assert.match(failedReports, /role="alert"/);
    assert.match(failedReports, /Saved reports are unavailable/);

    const savedReport: StoredReport = {
      report_id: "33333333-3333-4333-8333-333333333333",
      research_session_id: storedReport.research_session_id,
      report:
        "# Weekly update\n\n**Revenue** grew [quickly](https://example.org/secret) with `code`.\n\n- one\n- two",
      citations: [web],
      verification: [
        { citation_id: "c1", support: "full", reason: "supported" },
      ],
      tool_rounds: 1,
      created_at: "2026-11-11T15:04:05+00:00",
    };
    const savedReportsHtml = renderToStaticMarkup(
      <PersistedReportsView
        reports={[savedReport]}
        loading={false}
      />,
    );
    assert.match(savedReportsHtml, /Saved reports/);
    assert.equal((savedReportsHtml.match(/<li /g) ?? []).length, 1);
    assert.ok(
      savedReportsHtml.includes('dateTime="2026-11-11T15:04:05+00:00"'),
    );
    assert.match(savedReportsHtml, /1 tool round\b/);
    assert.match(savedReportsHtml, /1 citation\b/);
    assert.match(savedReportsHtml, /aria-expanded="false"/);
    assert.match(
      savedReportsHtml,
      /Weekly update Revenue grew quickly with code\. one two/,
    );
    assert.ok(!savedReportsHtml.includes("example.org/secret"));
    assert.ok(!savedReportsHtml.includes("**"));
    // Collapsed rows are text-only: the full Markdown view and Sources render
    // only after a row is expanded.
    assert.ok(!savedReportsHtml.includes("markdown-content"));
    assert.ok(!savedReportsHtml.includes("Latest completed research sources"));

    const longReport: StoredReport = {
      ...savedReport,
      report_id: "44444444-4444-4444-8444-444444444444",
      report: "word ".repeat(100),
    };
    const longExcerpt = /<span class="min-w-0 truncate">([^<]*)<\/span>/.exec(
      renderToStaticMarkup(
        <PersistedReportsView
          reports={[longReport]}
          loading={false}
        />,
      ),
    )?.[1];
    assert.ok(longExcerpt);
    assert.ok(longExcerpt.endsWith("…"));
    assert.ok(Array.from(longExcerpt).length <= 141);
    assert.ok(!longExcerpt.includes("#"));

    console.log(
      "PASS: multipart bytes/MIME, Document order/errors, Reports URL/encoding/header/errors/empty/loading/excerpt, Sources shape/order/duplicates/escaping/links/lifecycle copy, citation anchors.",
    );
  } finally {
    globalThis.fetch = originalFetch;
    if (originalBackend === undefined)
      delete process.env.NEXT_PUBLIC_BACKEND_URL;
    else process.env.NEXT_PUBLIC_BACKEND_URL = originalBackend;
    if (originalUser === undefined)
      delete process.env.NEXT_PUBLIC_RESEARCHFLOW_USER_ID;
    else process.env.NEXT_PUBLIC_RESEARCHFLOW_USER_ID = originalUser;
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
