// Focused module check, not the P8-QA-001 real-stack browser acceptance.
// Run the two commands documented in frontend/README.md.
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import {
  documentErrorMessage,
  listProjectDocuments,
  uploadProjectDocument,
} from "../src/lib/backend";
import { safeSourceUrl, type Citation } from "../src/lib/citations";
import { LatestResearchSources } from "../src/components/thread/sources";

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
    console.log(
      "PASS: multipart bytes/MIME, Document order/errors, Sources shape/order/duplicates/escaping/links/lifecycle copy.",
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
