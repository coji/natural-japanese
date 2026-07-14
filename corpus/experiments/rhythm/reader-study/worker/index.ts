import INDEX_HTML from "../index.html";
import STIMULI from "../stimuli.json";

const CONDITIONS = ["uniform", "varied", "control"] as const;
type Condition = (typeof CONDITIONS)[number];

type Answer = {
  item_id: string;
  condition: string;
  monotony: number;
  naturalness: number;
  readability: number;
  comprehension: number;
  elapsed_ms: number;
};

type Submission = {
  participant_id: string;
  attention_check: number;
  answers: Answer[];
};

type AssignedItem = {
  id: string;
  genre: string;
  condition: Condition;
  text: string;
  question: { prompt: string; choices: string[] };
};

function json(data: unknown, status = 200): Response {
  return Response.json(data, {
    status,
    headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" },
  });
}

async function digest(participantId: string): Promise<Uint8Array> {
  const bytes = new TextEncoder().encode(participantId);
  return new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
}

function uint64(bytes: Uint8Array): bigint {
  let value = 0n;
  for (const byte of bytes.slice(1, 9)) value = (value << 8n) | BigInt(byte);
  return value;
}

function nextRandom(state: bigint): [bigint, number] {
  const mask = (1n << 64n) - 1n;
  let next = state;
  next ^= next << 13n;
  next ^= next >> 7n;
  next ^= next << 17n;
  next &= mask;
  return [next, Number(next >> 11n) / 2 ** 53];
}

async function assignment(participantId: string): Promise<AssignedItem[]> {
  const hash = await digest(participantId);
  const listIndex = (hash[0] ?? 0) % 3;
  const assigned: AssignedItem[] = STIMULI.map((item, index) => {
    const condition = CONDITIONS[(index + listIndex) % 3] ?? "control";
    return {
      id: item.id,
      genre: item.genre,
      condition,
      text: item.variants[condition],
      question: { prompt: item.question.prompt, choices: item.question.choices },
    };
  });
  let state = uint64(hash) || 1n;
  for (let index = assigned.length - 1; index > 0; index -= 1) {
    let random: number;
    [state, random] = nextRandom(state);
    const other = Math.floor(random * (index + 1));
    [assigned[index], assigned[other]] = [assigned[other]!, assigned[index]!];
  }
  return assigned;
}

function isIntegerIn(value: unknown, minimum: number, maximum: number): value is number {
  return Number.isInteger(value) && Number(value) >= minimum && Number(value) <= maximum;
}

function parseSubmission(value: unknown): Submission | null {
  if (typeof value !== "object" || value === null) return null;
  const candidate = value as Record<string, unknown>;
  if (typeof candidate.participant_id !== "string" || candidate.participant_id.length < 16 || candidate.participant_id.length > 64) return null;
  if (!isIntegerIn(candidate.attention_check, 1, 7) || !Array.isArray(candidate.answers) || candidate.answers.length !== 12) return null;
  const answers: Answer[] = [];
  for (const valueAnswer of candidate.answers) {
    if (typeof valueAnswer !== "object" || valueAnswer === null) return null;
    const answer = valueAnswer as Record<string, unknown>;
    if (typeof answer.item_id !== "string" || typeof answer.condition !== "string") return null;
    if (!isIntegerIn(answer.monotony, 1, 7) || !isIntegerIn(answer.naturalness, 1, 7) || !isIntegerIn(answer.readability, 1, 7)) return null;
    if (!isIntegerIn(answer.comprehension, 0, 2) || !isIntegerIn(answer.elapsed_ms, 1_000, 1_800_000)) return null;
    answers.push({
      item_id: answer.item_id, condition: answer.condition, monotony: answer.monotony,
      naturalness: answer.naturalness, readability: answer.readability,
      comprehension: answer.comprehension, elapsed_ms: answer.elapsed_ms,
    });
  }
  return { participant_id: candidate.participant_id, attention_check: candidate.attention_check, answers };
}

async function validateSubmission(value: unknown): Promise<{ submission: Submission } | { error: string }> {
  const submission = parseSubmission(value);
  if (!submission) return { error: "回答形式が不正です" };
  const expected = new Map((await assignment(submission.participant_id)).map((item) => [item.id, item.condition]));
  const seen = new Set<string>();
  for (const answer of submission.answers) {
    if (seen.has(answer.item_id) || expected.get(answer.item_id) !== answer.condition) return { error: "刺激IDまたは条件割付が不正です" };
    seen.add(answer.item_id);
  }
  return { submission };
}

async function handle(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  if (request.method === "GET" && url.pathname === "/") {
    return new Response(INDEX_HTML, {
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
      },
    });
  }
  if (request.method === "GET" && url.pathname === "/healthz") return json({ ok: true });
  if (request.method === "GET" && url.pathname === "/api/session") {
    const participantId = crypto.randomUUID();
    return json({ participant_id: participantId, items: await assignment(participantId) });
  }
  if (request.method === "POST" && url.pathname === "/api/submit") {
    const contentLength = Number(request.headers.get("Content-Length") ?? "0");
    if (contentLength > 100_000) return json({ ok: false, error: "回答データが大きすぎます" }, 413);
    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return json({ ok: false, error: "JSONが不正です" }, 400);
    }
    const validated = await validateSubmission(body);
    if ("error" in validated) return json({ ok: false, error: validated.error }, 400);
    const submission = validated.submission;
    try {
      await env.DB.prepare("INSERT INTO submissions (participant_id, received_at, payload_json) VALUES (?, ?, ?)")
        .bind(submission.participant_id, new Date().toISOString(), JSON.stringify({
          schema_version: 1,
          received_at: new Date().toISOString(),
          participant_id: submission.participant_id,
          attention_check: submission.attention_check,
          answers: submission.answers,
        })).run();
    } catch (error) {
      if (error instanceof Error && error.message.includes("UNIQUE constraint failed")) return json({ ok: false, error: "この回答は送信済みです" }, 409);
      throw error;
    }
    return json({ ok: true }, 201);
  }
  return json({ ok: false, error: "Not found" }, 404);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      return await handle(request, env);
    } catch (error) {
      console.error(JSON.stringify({ message: "request failed", path: new URL(request.url).pathname,
        error: error instanceof Error ? error.message : String(error) }));
      return json({ ok: false, error: "サーバーエラーが発生しました" }, 500);
    }
  },
} satisfies ExportedHandler<Env>;
