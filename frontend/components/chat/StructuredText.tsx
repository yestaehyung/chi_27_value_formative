// 에이전트 답변의 경량 구조 렌더러 (2026-08-06).
//
// 왜 마크다운 라이브러리를 안 쓰나: 프론트 의존성이 react/react-dom/next 셋뿐인 프로젝트다.
// react-markdown + remark-gfm는 번들과 XSS 표면을 함께 들여온다. 에이전트가 실제로 쓰는
// 구조는 **불릿 · 번호 목록 · 표 · 굵게** 넷뿐이라, 그만 파싱하고 나머지는 평문으로 둔다.
// 파싱하지 않은 문법은 그대로 글자로 보일 뿐 실행되지 않는다(React가 텍스트로 이스케이프).
//
// 지원 문법
//   - 항목        · 항목        1. 항목        ← 목록
//   | 열 | 열 |   구분행(---)은 있어도 없어도 됨   ← 표
//   **강조**                                    ← 굵게 (인라인)
//
// 지원하지 않는 것(의도): 제목(#), 코드블록, 링크, 이미지, 인용.
// 쇼핑 대화에 필요 없고, 참가자 화면을 문서처럼 보이게 만든다.

import { Fragment, type ReactNode } from "react";

/** **굵게**만 인라인 처리. 나머지는 그대로 텍스트. */
function inline(text: string): ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) =>
    p.startsWith("**") && p.endsWith("**") && p.length > 4 ? (
      <strong key={i} className="font-semibold text-[#191919]">{p.slice(2, -2)}</strong>
    ) : (
      <Fragment key={i}>{p}</Fragment>
    ),
  );
}

const isTableRow = (l: string) => /^\s*\|.*\|\s*$/.test(l);
/** |---|---| 같은 정렬 구분행 — 렌더하지 않는다. */
const isTableDivider = (l: string) => /^\s*\|[\s:|-]+\|\s*$/.test(l);
const cells = (l: string) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

const BULLET = /^\s*[-*·•]\s+(.*)$/;
const NUMBERED = /^\s*(\d+)[.)]\s+(.*)$/;

type Block =
  | { kind: "p"; lines: string[] }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] }
  | { kind: "table"; rows: string[][] };

/** 줄 단위로 블록을 모은다 — 같은 종류가 연속되면 한 블록으로 묶인다. */
function parse(content: string): Block[] {
  const lines = content.split("\n");
  const blocks: Block[] = [];
  let cur: Block | null = null;
  const flush = () => { if (cur) blocks.push(cur); cur = null; };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) { flush(); continue; }

    if (isTableRow(line)) {
      if (isTableDivider(line)) continue;              // 구분행은 버린다
      if (cur?.kind !== "table") { flush(); cur = { kind: "table", rows: [] }; }
      (cur as { kind: "table"; rows: string[][] }).rows.push(cells(line));
      continue;
    }
    const num = line.match(NUMBERED);
    if (num) {
      if (cur?.kind !== "ol") { flush(); cur = { kind: "ol", items: [] }; }
      (cur as { kind: "ol"; items: string[] }).items.push(num[2]);
      continue;
    }
    const bul = line.match(BULLET);
    if (bul) {
      if (cur?.kind !== "ul") { flush(); cur = { kind: "ul", items: [] }; }
      (cur as { kind: "ul"; items: string[] }).items.push(bul[1]);
      continue;
    }
    if (cur?.kind !== "p") { flush(); cur = { kind: "p", lines: [] }; }
    (cur as { kind: "p"; lines: string[] }).lines.push(line);
  }
  flush();
  return blocks;
}

export default function StructuredText({ content }: { content: string }) {
  // 추천 항목("A. … B. …")이 한 줄로 붙어 나오면 항목 앞에서 줄바꿈 (기존 동작 유지)
  const normalized = content.replace(/([.!?…)\]]\s)([A-E]\.\s)/g, "$1\n$2");
  const blocks = parse(normalized);

  return (
    <div className="space-y-2.5">
      {blocks.map((b, i) => {
        if (b.kind === "ul") {
          return (
            <ul key={i} className="space-y-1 pl-1">
              {b.items.map((it, j) => (
                <li key={j} className="flex gap-2">
                  <span aria-hidden className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-[#9aa0a6]" />
                  <span className="min-w-0 flex-1">{inline(it)}</span>
                </li>
              ))}
            </ul>
          );
        }
        if (b.kind === "ol") {
          return (
            <ol key={i} className="space-y-1 pl-1">
              {b.items.map((it, j) => (
                <li key={j} className="flex gap-2">
                  <span className="shrink-0 font-semibold text-[#9aa0a6]">{j + 1}.</span>
                  <span className="min-w-0 flex-1">{inline(it)}</span>
                </li>
              ))}
            </ol>
          );
        }
        if (b.kind === "table") {
          const [head, ...body] = b.rows;
          return (
            // 좁은 화면에서 표가 말풍선을 밀어내지 않도록 가로 스크롤을 표 안에 가둔다
            <div key={i} className="-mx-1 overflow-x-auto">
              <table className="w-full border-collapse text-[13px]">
                <thead>
                  <tr>
                    {head.map((h, j) => (
                      <th key={j} className="border-b border-[#e4e8eb] px-2 py-1.5 text-left font-semibold text-[#5f6368]">
                        {inline(h)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {body.map((row, j) => (
                    <tr key={j} className="border-b border-[#f0f2f4] last:border-0">
                      {row.map((c, k) => (
                        <td key={k} className="px-2 py-1.5 align-top text-[#191919]">{inline(c)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        return (
          <p key={i} className="whitespace-pre-wrap">{inline(b.lines.join("\n"))}</p>
        );
      })}
    </div>
  );
}
