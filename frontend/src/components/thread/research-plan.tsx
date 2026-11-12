import { useId } from "react";

export function ResearchPlan({
  researchQuery,
  subQuestions,
  toolRounds,
}: {
  researchQuery?: string;
  subQuestions?: string[];
  toolRounds?: number;
}) {
  const headingId = useId();
  if (!subQuestions?.length) return null;

  return (
    <section
      aria-labelledby={headingId}
      className="min-w-0 rounded-lg border p-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2
          id={headingId}
          className="font-semibold"
        >
          Research plan
        </h2>
        {toolRounds !== undefined && (
          <span className="text-muted-foreground text-xs">
            {toolRounds} tool round{toolRounds === 1 ? "" : "s"}
          </span>
        )}
      </div>
      {researchQuery ? (
        <p className="text-muted-foreground mt-1 text-sm">{researchQuery}</p>
      ) : null}
      <ol className="mt-3 flex list-decimal flex-col gap-1 pl-5 text-sm">
        {subQuestions.map((question, index) => (
          <li
            key={index}
            className="min-w-0 break-words"
          >
            {question}
          </li>
        ))}
      </ol>
    </section>
  );
}
