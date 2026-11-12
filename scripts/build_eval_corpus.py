"""Build a retrieval evaluation corpus from real, locally installed documentation.

The previous evaluation corpus was hand-authored and small (~20 chunks per
Project), and a later attempt to grow it appended generated filler: 1,320
paragraphs that collapsed to six templates. Neither is a good basis for a
retrieval number.

This builder uses something that is both real and already on disk: the README
files of the packages in ``frontend/node_modules``. They are third-party open
source documentation with per-package licences, written by many different
authors for six distinguishable purposes, and they are exactly the kind of
prose a documentation assistant is asked to search.

The on-disk dataset schema allows at most six documents per Project, so each
Project is compiled into six volumes; every volume concatenates several package
READMEs with an attribution heading and the licence that package declares.

Usage::

    py -3.12 -m scripts.build_eval_corpus --out evaluations/datasets/retrieval_v4.json
    py -3.12 -m scripts.build_eval_corpus --dry-run

Requires an installed frontend (``pnpm install``); the builder never touches the
network and the produced dataset embeds the text, so the evaluation itself does
not depend on ``node_modules``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from researchflow.knowledge.chunking import CHUNK_OVERLAP_CHARS, MAX_CHUNK_CHARS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_NODE_MODULES = PROJECT_ROOT / "frontend" / "node_modules"

DATASET_VERSION = "retrieval-v4"
VOLUMES_PER_PROJECT = 6
PACKAGES_PER_PROJECT = 42
MIN_PACKAGE_BYTES = 2000
MAX_PACKAGE_BYTES = 200_000
MAX_VOLUME_BYTES = 1_000_000

README_NAMES = {"readme.md", "readme.markdown", "readme"}

# Ordered: the first matching domain wins, so put the specific families first.
DOMAINS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "markdown-pipeline",
        "Markdown, MDAST/HAST and syntax highlighting",
        (
            "micromark",
            "mdast",
            "hast",
            "unist",
            "unified",
            "remark",
            "rehype",
            "vfile",
            "character-entities",
            "stringify-entities",
            "parse-entities",
            "property-information",
            "web-namespaces",
            "zwitch",
            "trough",
            "bail",
            "devlop",
            "markdown-table",
            "trim-lines",
            "longest-streak",
            "comma-separated-tokens",
            "space-separated-tokens",
            "decode-named-character-reference",
            "fault",
            "lowlight",
            "highlight.js",
            "refractor",
            "prismjs",
            "prism-react-renderer",
            "katex",
            "react-markdown",
            "react-syntax-highlighter",
            "style-to-object",
            "style-to-js",
            "html-url-attributes",
            "inline-style-parser",
        ),
    ),
    (
        "data-visualisation",
        "Chart geometry, scales and rendering",
        (
            "d3-",
            "recharts",
            "victory",
            "react-smooth",
            "internmap",
            "decimal.js-light",
            "fraction.js",
            "dom-helpers",
            "css-vendor",
        ),
    ),
    (
        "build-and-tooling",
        "Bundling, CSS processing and module resolution",
        (
            "esbuild",
            "enhanced-resolve",
            "tapable",
            "postcss",
            "lightningcss",
            "cssesc",
            "icss-utils",
            "loader-utils",
            "magic-string",
            "jiti",
            "sharp",
            "browserslist",
            "electron-to-chromium",
            "semver",
            "tsconfig-paths",
            "unrs-resolver",
            "fdir",
            "detect-libc",
            "napi-postinstall",
            "styled-jsx",
            "source-map-js",
            "convert-source-map",
            "jridgewell",
            "acorn",
            "espree",
            "esquery",
            "esrecurse",
            "estraverse",
            "esutils",
            "gensync",
            "json5",
        ),
    ),
    (
        "testing-and-lint",
        "Linting, formatting and test tooling",
        (
            "eslint",
            "humanfs",
            "humanwhocodes",
            "prettier",
            "playwright",
            "axe-core",
            "jsx-ast-utils",
            "ast-types-flow",
            "aria-",
            "doctrine",
            "optionator",
            "levn",
            "type-check",
            "file-entry-cache",
            "flat-cache",
            "ignore",
            "glob-parent",
            "minimatch",
            "picomatch",
            "braces",
            "micromatch",
            "fast-glob",
            "natural-compare",
            "imurmurhash",
            "word-wrap",
            "json-stable-stringify",
            "fast-levenshtein",
        ),
    ),
    (
        "http-and-async-runtime",
        "HTTP clients, streaming and async primitives",
        (
            "node-fetch",
            "openai",
            "langsmith",
            "langchain",
            "langgraph",
            "p-queue",
            "p-retry",
            "p-limit",
            "p-timeout",
            "p-locate",
            "yocto-queue",
            "fastq",
            "reusify",
            "queue-microtask",
            "run-parallel",
            "run-parallel-limit",
            "agentkeepalive",
            "form-data",
            "combined-stream",
            "delayed-stream",
            "asynckit",
            "mime-db",
            "mime-types",
            "whatwg-url",
            "webidl-conversions",
            "abort-controller",
            "event-target-shim",
            "web-streams-polyfill",
            "formdata-node",
            "eventemitter3",
            "merge2",
            "async-sema",
        ),
    ),
)

UTILITIES_DOMAIN = (
    "schemas-and-utilities",
    "Validation, parsing helpers and general utilities",
)

_BADGE_LINE = re.compile(r"^\s*(\[!\[|!\[|<img|<p align|<a [^>]*>\s*<img)")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_MULTI_BLANK = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class PackageDoc:
    name: str
    path: Path
    license: str
    text: str

    @property
    def size(self) -> int:
        return len(self.text)


def _read_license(readme: Path) -> str:
    manifest = readme.parent / "package.json"
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "UNKNOWN"
    license_value = raw.get("license") or raw.get("licenses") or "UNKNOWN"
    if isinstance(license_value, dict):
        license_value = license_value.get("type") or "UNKNOWN"
    if isinstance(license_value, list):
        license_value = ", ".join(str(item) for item in license_value)
    return str(license_value)


def _clean(text: str) -> str:
    text = _COMMENT.sub("", text)
    kept: list[str] = []
    for line in text.splitlines():
        if _BADGE_LINE.match(line):
            continue
        if line.strip().startswith("[![") or line.strip().startswith("!["):
            continue
        kept.append(line.rstrip())
    return _MULTI_BLANK.sub("\n\n", "\n".join(kept)).strip()


def _package_name(path: Path) -> str:
    parts = path.parts
    index = max(i for i, part in enumerate(parts) if part == "node_modules")
    return "/".join(parts[index + 1 : -1])


def collect_packages(node_modules: Path) -> dict[str, PackageDoc]:
    """One README per package name, preferring the largest copy."""

    if not node_modules.is_dir():
        raise SystemExit(
            f"{node_modules} does not exist; run `pnpm install` in frontend/ first"
        )

    best: dict[str, PackageDoc] = {}
    for path in node_modules.rglob("*"):
        if not path.is_file() or path.name.lower() not in README_NAMES:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size < MIN_PACKAGE_BYTES or size > MAX_PACKAGE_BYTES:
            continue
        if "/licenses/" in path.as_posix():
            continue
        name = _package_name(path)
        if not name:
            continue
        text = _clean(path.read_text(encoding="utf-8", errors="replace"))
        if len(text) < MIN_PACKAGE_BYTES // 2:
            continue
        document = PackageDoc(name=name, path=path, license=_read_license(path), text=text)
        previous = best.get(name)
        if previous is None or document.size > previous.size:
            best[name] = document
    return best


def classify(name: str) -> str:
    lowered = name.lower()
    for domain_key, _label, markers in DOMAINS:
        if any(marker in lowered for marker in markers):
            return domain_key
    return UTILITIES_DOMAIN[0]


def _domain_labels() -> dict[str, str]:
    labels = {key: label for key, label, _ in DOMAINS}
    labels[UTILITIES_DOMAIN[0]] = UTILITIES_DOMAIN[1]
    return labels


def _deduplicate_chunks(content: str) -> str:
    """Drop repeated chunk texts inside one volume.

    Packages from the same family often repeat a section verbatim (p-queue
    embeds p-limit's docs, several mdast packages share boilerplate). A corpus
    must not contain the same passage twice: the live runner maps a search hit
    back to its chunk by ``(document, text)``, so a duplicate makes the mapping
    ambiguous, and a duplicate also wastes a top-k slot on an identical string.
    """

    from researchflow.knowledge.chunking import CHUNK_OVERLAP_CHARS, MAX_CHUNK_CHARS, chunk_markdown

    seen: set[str] = set()
    kept: list[str] = []
    for chunk in chunk_markdown(content):
        text = chunk.content.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        kept.append(text)

    return "\n\n".join(kept) + "\n"


def build_volumes(
    packages: list[PackageDoc], *, project_key: str, project_name: str
) -> list[dict[str, str]]:
    """Spread packages across exactly VOLUMES_PER_PROJECT documents."""

    buckets: list[list[PackageDoc]] = [[] for _ in range(VOLUMES_PER_PROJECT)]
    for index, package in enumerate(packages):
        buckets[index % VOLUMES_PER_PROJECT].append(package)

    volumes: list[dict[str, str]] = []
    for number, bucket in enumerate(buckets, start=1):
        if not bucket:
            continue
        parts = [
            f"# {project_name} — volume {number}",
            "",
            "Compiled from third-party package documentation. Each section records "
            "the package it came from and the licence that package declares.",
            "",
        ]
        for package in sorted(bucket, key=lambda item: item.name):
            parts.append(f"## {package.name}")
            parts.append("")
            parts.append(f"Source: `{package.name}` README (licence: {package.license}).")
            parts.append("")
            parts.append(package.text)
            parts.append("")
        content = "\n".join(parts).strip() + "\n"
        content = _deduplicate_chunks(content)
        if len(content.encode("utf-8")) > MAX_VOLUME_BYTES:
            raise SystemExit(
                f"{project_key} volume {number} exceeds the 1 MiB document limit"
            )
        volumes.append(
            {
                "document_key": f"{project_key}-volume-{number}",
                "filename": f"{project_key}-volume-{number}.md",
                "content": content,
            }
        )
    return volumes


def render_sources_manifest(dataset: dict) -> str:
    """List every compiled package with its licence, for attribution."""

    rows: list[str] = [
        "# Corpus sources",
        "",
        "Every document in `retrieval_v4.json` is compiled from the README files of",
        "packages installed under `frontend/node_modules`. Text is reproduced",
        "unmodified apart from stripping HTML comments and badge lines. Each section",
        "inside a volume names its package; this table records the licence each",
        "package declares in its `package.json`.",
        "",
        "| Project | Volume | Package | Licence |",
        "| --- | --- | --- | --- |",
    ]

    for project in dataset["projects"]:
        for document in project["documents"]:
            for line in document["content"].splitlines():
                if line.startswith("Source: `"):
                    package = line.split("`")[1]
                    licence = line.split("licence: ", 1)[-1].rstrip(").")
                    rows.append(
                        f"| {project['project_key']} | {document['document_key']} | "
                        f"`{package}` | {licence} |"
                    )
    rows.append("")
    return "\n".join(rows)


def build_dataset(
    node_modules: Path,
    *,
    cases_path: Path | None = None,
    cases_dir: Path | None = None,
) -> dict:
    packages = collect_packages(node_modules)

    grouped: dict[str, list[PackageDoc]] = {}
    for package in packages.values():
        grouped.setdefault(classify(package.name), []).append(package)

    labels = _domain_labels()
    projects: list[dict] = []
    report: list[str] = []

    for project_key in sorted(grouped):
        members = sorted(grouped[project_key], key=lambda item: -item.size)[
            :PACKAGES_PER_PROJECT
        ]
        if len(members) < 6:
            report.append(f"skip {project_key}: only {len(members)} packages")
            continue
        project_name = labels.get(project_key, project_key)
        volumes = build_volumes(members, project_key=project_key, project_name=project_name)
        projects.append(
            {
                "project_key": project_key,
                "name": project_name,
                "documents": volumes,
            }
        )
        report.append(
            f"{project_key:<26} packages={len(members):>3} volumes={len(volumes)} "
            f"chars={sum(len(v['content']) for v in volumes):>8}"
        )

    cases: list[dict] = []
    if cases_path is not None:
        cases = json.loads(cases_path.read_text(encoding="utf-8-sig"))
    if cases_dir is not None:
        for fragment in sorted(cases_dir.glob("*.json")):
            payload = json.loads(fragment.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, list):
                raise SystemExit(f"{fragment}: expected a JSON array of cases")
            cases.extend(payload)

    dataset = {
        "schema_version": 2,
        "dataset_version": DATASET_VERSION,
        "label_review": "synthetic_ai_reviewed",
        "label_note": (
            "Documents are unmodified README files of third-party open source "
            "packages installed under frontend/node_modules, compiled into six "
            "volumes per Project. Each section names its package and the licence "
            "that package declares. Relevance labels are answered only by the "
            "cited passage and are checked against the production chunker "
            f"(max {MAX_CHUNK_CHARS} chars, overlap {CHUNK_OVERLAP_CHARS})."
        ),
        "chunking": {"max_chars": MAX_CHUNK_CHARS, "overlap_chars": CHUNK_OVERLAP_CHARS},
        "projects": projects,
        "cases": cases,
    }
    return dataset, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-modules", type=Path, default=DEFAULT_NODE_MODULES)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--cases",
        type=Path,
        default=None,
        help="JSON array of cases to embed; omit to emit an empty case list",
    )
    parser.add_argument(
        "--cases-dir",
        type=Path,
        default=None,
        help="directory of JSON case fragments to merge, in filename order",
    )
    parser.add_argument(
        "--sources-out",
        type=Path,
        default=None,
        help="write a Markdown table of package -> licence attribution",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    dataset, report = build_dataset(
        args.node_modules, cases_path=args.cases, cases_dir=args.cases_dir
    )

    for line in report:
        print(line)

    from researchflow.knowledge.chunking import CHUNK_OVERLAP_CHARS, MAX_CHUNK_CHARS, chunk_markdown

    total_chunks = 0
    print()
    for project in dataset["projects"]:
        chunks = [len(chunk_markdown(doc["content"])) for doc in project["documents"]]
        total_chunks += sum(chunks)
        print(
            f"{project['project_key']:<26} chunks={sum(chunks):>4} "
            f"per-volume={chunks} docs={len(project['documents'])}"
        )
    print()
    print("projects:", len(dataset["projects"]), "| total chunks:", total_chunks,
          "| cases:", len(dataset["cases"]))

    if args.dry_run or args.out is None:
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(dataset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("wrote", args.out)

    if args.sources_out is not None:
        args.sources_out.parent.mkdir(parents=True, exist_ok=True)
        args.sources_out.write_text(render_sources_manifest(dataset), encoding="utf-8")
        print("wrote", args.sources_out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
