"""Aggregate statistics of the project's history, for the paper's "process" section.

Commit part (reproducible from this repository):  git log, trailers, numstat.
Session part (optional, needs the agent's local session logs, which are not in the
repository):  python docs/paper/make_process_stats.py --sessions ~/.claude/projects/<project>
Only counts are stored: no prompts, no file contents, no identifiers.
"""
import argparse, collections, datetime as dt, glob, json, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "process_stats.json")
CODE = re.compile(r"^(src/.*\.py|tests/.*\.py|docs/.*\.py)$")
MODEL_RE = re.compile(r"Co-authored-by:\s*Claude ([A-Za-z]+ [0-9.]+)", re.I)


def commits(rev: str = "HEAD") -> list[dict]:
    raw = subprocess.run(["git", "log", rev, "--reverse", "--date=short", "--numstat", "--format=%x01%h|%ad|%s%n%b%x02"],
                         capture_output=True, text=True, check=True).stdout
    out = []
    for blk in raw.split("\x01")[1:]:
        head, _, rest = blk.partition("\x02")
        lines = head.strip("\n").split("\n")
        h, d, s = lines[0].split("|", 2)
        models = sorted(set(MODEL_RE.findall("\n".join(lines[1:]))))
        add = dele = code_add = code_del = files = 0
        for ln in rest.strip("\n").split("\n"):
            p = ln.split("\t")
            if len(p) == 3 and p[0].isdigit():
                files += 1
                if CODE.match(p[2]):
                    code_add += int(p[0]); code_del += int(p[1])
        out.append(dict(h=h, d=d, s=s, models=models, files=files, code_add=code_add, code_del=code_del,
                        type=(re.match(r"^(\w+)", s).group(1).lower() if re.match(r"^(\w+)", s) else "other")))
    return out


def sessions(root: str) -> dict:
    P = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    mains = [f for f in glob.glob(os.path.join(root, "*.jsonl")) if "orphaned" not in f]
    subs = glob.glob(os.path.join(root, "*", "subagents", "*.jsonl")) + glob.glob(os.path.join(root, "*", "*", "subagents", "*.jsonl"))
    turns, out_tok = collections.Counter(), collections.Counter()
    sub_turns = collections.Counter()
    tools, span = collections.Counter(), {}
    day_turns = collections.defaultdict(collections.Counter)
    humans, stamps = 0, []
    for f in mains + subs:
        is_sub = f in subs
        for line in open(f, errors="ignore"):
            try:
                o = json.loads(line)
            except ValueError:
                continue
            m, ts = o.get("message"), o.get("timestamp")
            if ts and not is_sub:
                stamps.append(P(ts))
            if o.get("type") == "assistant" and isinstance(m, dict) and m.get("model") not in (None, "<synthetic>"):
                mod = m["model"]
                (sub_turns if is_sub else turns)[mod] += 1
                out_tok[mod] += (m.get("usage") or {}).get("output_tokens", 0) or 0
                if not is_sub:
                    lo, hi = span.get(mod, (ts, ts))
                    span[mod] = (min(lo, ts), max(hi, ts))
                    day_turns[ts[:10]][mod] += 1
                for c in m.get("content", []) if isinstance(m.get("content"), list) else []:
                    if c.get("type") == "tool_use":
                        tools[("sub:" if is_sub else "") + c.get("name", "?")] += 1
            elif o.get("type") == "user" and not is_sub and isinstance(m, dict) and not o.get("isSidechain") and not o.get("isMeta"):
                c = m.get("content")
                txt = c if isinstance(c, str) else next((x.get("text", "") for x in c if x.get("type") == "text"), "") if isinstance(c, list) else ""
                if txt and not txt.lstrip().startswith("<") and len(txt) > 3:
                    humans += 1
    stamps.sort()
    active, per_day = dt.timedelta(), collections.defaultdict(float)
    for a, b in zip(stamps, stamps[1:]):
        if b - a <= dt.timedelta(minutes=20):
            active += b - a
            per_day[str(a.date())] += (b - a).total_seconds() / 3600
    return {"main_turns": dict(turns), "subagent_turns": dict(sub_turns), "output_tokens": dict(out_tok),
            "model_span_main_thread": {k: [v[0][:10], v[1][:10]] for k, v in span.items()},
            "tool_calls": dict(tools.most_common(20)), "engineer_messages": humans,
            "subagent_sessions": len(subs), "main_sessions": len(mains),
            "active_hours": round(active.total_seconds() / 3600, 1),
            "active_hours_per_day": {k: round(v, 2) for k, v in sorted(per_day.items())},
            "idle_gap_minutes": 20}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upto", default="4d570ac", help="last commit counted (the paper quotes the history up to here)")
    ap.add_argument("--sessions", help="directory with the agent's session logs (optional)")
    a = ap.parse_args()
    cs = commits(a.upto)
    per_model = collections.Counter(m for c in cs for m in c["models"])
    res = {"upto": a.upto, "commits": len(cs), "first": cs[0]["d"], "last": cs[-1]["d"],
           "with_agent_trailer": sum(bool(c["models"]) for c in cs),
           "by_model": dict(per_model.most_common()),
           "by_type": dict(collections.Counter(c["type"] for c in cs).most_common()),
           "fix_by_model": dict(collections.Counter(m for c in cs if c["type"] == "fix" for m in c["models"]).most_common()),
           "per_day": {d: {"all": n, "agent": sum(1 for c in cs if c["d"] == d and c["models"]),
                           "models": dict(collections.Counter(m for c in cs if c["d"] == d for m in c["models"]))}
                       for d, n in sorted(collections.Counter(c["d"] for c in cs).items())},
           "active_days": len({c["d"] for c in cs}),
           "code_lines_added": sum(c["code_add"] for c in cs), "code_lines_deleted": sum(c["code_del"] for c in cs),
           "median_files_per_commit": sorted(c["files"] for c in cs)[len(cs) // 2]}
    if a.sessions:
        res["sessions"] = sessions(os.path.expanduser(a.sessions))
    elif os.path.exists(OUT):                      # keep the session part from an earlier run
        old = json.load(open(OUT))
        if "sessions" in old:
            res["sessions"] = old["sessions"]
    json.dump(res, open(OUT, "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ("per_day",)}, indent=1)[:3000])


if __name__ == "__main__":
    main()
