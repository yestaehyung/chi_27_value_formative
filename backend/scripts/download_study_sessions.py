#!/usr/bin/env python3
"""Download live ValueCommit study sessions to local JSON + readable Markdown.

The live deploy bundles a whole session (conversation + recommendation list +
feedback) in ONE call: GET /api/research/sessions/{id}/replay. We dump that raw
(lossless `.json`) and render a human-readable transcript (`.md`) that inlines
the recommendation cards under each agent turn (linked by `turnId`).

Survey answers are NOT in the replay (they live on Participant) — fetched
separately via /api/research/participants/{id}/survey when --survey is set.

Usage (from valuecommit/backend, no deps beyond stdlib):
    python3 scripts/download_study_sessions.py part_9c03a2f842      # one participant's sessions
    python3 scripts/download_study_sessions.py --all               # every session (incl. dummy)
    python3 scripts/download_study_sessions.py --real              # skip obvious test/junk
    python3 scripts/download_study_sessions.py part_xxx --survey   # also save survey.json/md
    BASE=http://localhost:8000 python3 scripts/download_study_sessions.py --all   # against local

Output: backend/data/study_export/{participantId or _all}/{sessionId}.{json,md} + index.md
Live base default = the Railway deploy (see memory: railway-live-deployment).
"""
import json, os, sys, urllib.request, datetime

BASE = os.environ.get("BASE", "https://agent-shopping.up.railway.app").rstrip("/")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/
EXPORT_ROOT = os.path.join(HERE, "data", "study_export")


def _research_key() -> str:
    """연구자 키 (라이브 research API는 X-Research-Key 필수 — 스터디 분리 2026-07-02).
    우선순위: VC_RESEARCH_KEY env → frontend/.env.local의 NEXT_PUBLIC_RESEARCH_KEY."""
    key = os.environ.get("VC_RESEARCH_KEY", "").strip()
    if key:
        return key
    env_local = os.path.join(os.path.dirname(HERE), "frontend", ".env.local")
    if os.path.exists(env_local):
        for line in open(env_local, encoding="utf-8"):
            if line.strip().startswith("NEXT_PUBLIC_RESEARCH_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


KEY = _research_key()


def get(path):
    req = urllib.request.Request(BASE + path, headers={"X-Research-Key": KEY} if KEY else {})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r)


def is_dummy(pid, sess):
    """Heuristic: obvious test/junk participants & empty sessions."""
    if pid and (pid.startswith("test_") or "검증" in (pid or "")):
        return True
    if sess and (sess.get("turnCount") or 0) < 2:
        return True
    return False


def ptitle(p):
    return (p or {}).get("title") or (p or {}).get("name") or (p or {}).get("id") or "?"


def hhmm(ts):
    if not ts:
        return "?"
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%m-%d %H:%M")
    except Exception:
        return ts[:16]


def render_md(sid, scn, d):
    turns, imps, fbs = d.get("turns", []), d.get("impressions", []), d.get("feedback", [])
    imp_by_turn, fb_by_turn = {}, {}
    for im in imps:
        imp_by_turn.setdefault(im.get("turnId"), []).append(im)
    for fb in fbs:
        fb_by_turn.setdefault(fb.get("turnId"), []).append(fb)
    ts = [t.get("createdAt") for t in turns if t.get("createdAt")]
    span = f"{hhmm(min(ts))} ~ {hhmm(max(ts))}" if ts else "?"
    L = [f"# {sid} — {scn}", "",
         f"- 턴 {len(turns)} · 추천 {len(imps)} · 피드백 {len(fbs)}",
         f"- 기간(turn 타임스탬프): {span}", "", "---", ""]
    for t in sorted(turns, key=lambda x: x.get("turnIndex", 0)):
        role = "🙋 사용자" if t.get("role") == "user" else "🤖 에이전트"
        L += [f"**[{t.get('turnIndex')}·{role}]** {t.get('content', '')}", ""]
        for im in sorted(imp_by_turn.get(t.get("id"), []), key=lambda x: x.get("rank", 0)):
            prod = im.get("product") or {}
            meta = []
            if prod.get("price") is not None:
                pr = prod["price"]
                meta.append(f"{pr:,}원" if isinstance(pr, (int, float)) else str(pr))
            if prod.get("rating") is not None:
                meta.append(f"★{prod['rating']}")
            L.append(f"  - 📦 **#{im.get('rank')}** {ptitle(prod)}" + (f" ({' · '.join(meta)})" if meta else ""))
            if im.get("recommendationReason"):
                L.append(f"      _{im['recommendationReason']}_")
            tags = " ".join(f"✓{x}" for x in (im.get("matchedIntentions") or [])) + \
                   (" " + " ".join(f"⚠{x}" for x in (im.get("weakIntentions") or [])) if im.get("weakIntentions") else "")
            if tags.strip():
                L.append(f"      {tags}")
        for fb in fb_by_turn.get(t.get("id"), []):
            icon = "👍" if fb.get("type") == "like" else "👎"
            rt = fb.get("reasonText") or fb.get("reasonCode") or ""
            L.append(f"  - {icon} 피드백 → `{fb.get('productId')}`" + (f' — "{rt}"' if rt else ""))
        if imp_by_turn.get(t.get("id")) or fb_by_turn.get(t.get("id")):
            L.append("")
    return "\n".join(L)


def main(argv):
    want_survey = "--survey" in argv
    args = [a for a in argv if not a.startswith("--")]
    mode = "all" if "--all" in argv else ("real" if "--real" in argv else (args[0] if args else None))
    if not mode:
        print(__doc__)
        sys.exit(1)

    sessions = get("/api/research/sessions").get("sessions", [])
    if mode not in ("all", "real"):
        sessions = [s for s in sessions if s.get("participantId") == mode]
        out_name = mode
    else:
        if mode == "real":
            sessions = [s for s in sessions if not is_dummy(s.get("participantId"), s)]
        out_name = "_all" if mode == "all" else "_real"
    if not sessions:
        print(f"no sessions for '{mode}'"); sys.exit(2)

    out_dir = os.path.join(EXPORT_ROOT, out_name)
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for s in sessions:
        sid, scn = s["id"], s.get("scenarioId", "?")
        d = get(f"/api/research/sessions/{sid}/replay")
        with open(os.path.join(out_dir, f"{sid}.json"), "w") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        with open(os.path.join(out_dir, f"{sid}.md"), "w") as f:
            f.write(render_md(sid, scn, d))
        rows.append((sid, scn, s.get("participantId"), len(d.get("turns", [])),
                     len(d.get("impressions", [])), len(d.get("feedback", []))))
        print(f"  {sid} ({scn}): turns={rows[-1][3]} imps={rows[-1][4]} fb={rows[-1][5]}")

    if want_survey:
        for pid in sorted({r[2] for r in rows if r[2]}):
            try:
                sv = get(f"/api/research/participants/{pid}/survey")
                with open(os.path.join(out_dir, f"survey_{pid}.json"), "w") as f:
                    json.dump(sv, f, ensure_ascii=False, indent=2)
                print(f"  survey {pid}: profile={sv.get('profile')}")
            except Exception as e:
                print(f"  survey {pid}: FAIL {e}")

    idx = [f"# study export — `{out_name}` (from {BASE})", "",
           "| 세션 | 시나리오 | 참가자 | 턴 | 추천 | 피드백 |",
           "|---|---|---|---|---|---|"]
    for sid, scn, pid, nt, ni, nf in rows:
        idx.append(f"| [{sid}]({sid}.md) | {scn} | {pid} | {nt} | {ni} | {nf} |")
    with open(os.path.join(out_dir, "index.md"), "w") as f:
        f.write("\n".join(idx))
    print(f"\n→ {out_dir}  ({len(rows)} sessions)")


if __name__ == "__main__":
    main(sys.argv[1:])
