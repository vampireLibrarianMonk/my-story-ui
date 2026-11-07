"""Model comparison harness for creative-writing tasks on AWS Bedrock.

Builds each prompt with the application's own helpers (app.intent.build_system_prompt / build_turns) so the
measured prompt is exactly what /api/chat would send, then calls bedrock-runtime.converse directly to capture
token usage, latency and cost that the production text-only adapter discards.

Pricing is read from tools/eval/pricing.json (USD per 1K tokens). Unknown models are measured in tokens only.
No app code path is mocked; a missing price is reported as unknown, never as zero.

  python -m tools.eval.harness --task character_profile --models amazon.nova-pro-v1:0,amazon.nova-lite-v1:0
  python -m tools.eval.harness --suite            # every task x every model in pricing.json
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import boto3

from app.intent import build_references, build_system_prompt, build_turns
from tools.eval import rubric
from tools.eval.corpus import load_context, load_tasks

ROOT = Path(__file__).resolve().parents[2]
PRICING = json.loads((ROOT / "tools" / "eval" / "pricing.json").read_text())
REPORTS = (
    ROOT / "dropbox_archive" / "eval"
)  # git-ignored: runs may contain generated prose


@dataclass
class Result:
    task: str
    model: str
    mode: str
    latency_s: float
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    blocks: int
    warnings: int
    findings: list[dict]
    text: str


def _converse_messages(turns: list[dict]) -> tuple[list[dict], list[dict]]:
    system = [{"text": t["content"]} for t in turns if t["role"] == "system"]
    msgs = [
        {"role": t["role"], "content": [{"text": t["content"]}]}
        for t in turns
        if t["role"] in ("user", "assistant")
    ]
    return system, msgs


def _cost(model: str, usage: dict) -> float | None:
    price = PRICING.get(model)
    if not price:
        return None
    return round(
        usage["inputTokens"] / 1000 * price["input"]
        + usage["outputTokens"] / 1000 * price["output"],
        6,
    )


def run_one(
    client, model: str, task: dict, rules: dict, max_tokens: int, temperature: float
) -> Result:
    docs = load_context(task.get("context", []))
    system = build_system_prompt(
        task["mode"],
        task.get("options", {}),
        build_references(docs),
        assist=task.get("assist", False),
    )
    turns = build_turns(system, [], task["prompt"])
    sys_block, msgs = _converse_messages(turns)

    t0 = time.time()
    resp = client.converse(
        modelId=model,
        system=sys_block,
        messages=msgs,
        inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
    )
    latency = time.time() - t0
    text = "".join(b.get("text", "") for b in resp["output"]["message"]["content"])
    usage = resp.get("usage", {"inputTokens": 0, "outputTokens": 0})

    rep = rubric.check(text, rules, context_titles=tuple(d["title"] for d in docs))
    return Result(
        task=task["id"],
        model=model,
        mode=task["mode"],
        latency_s=round(latency, 2),
        input_tokens=usage["inputTokens"],
        output_tokens=usage["outputTokens"],
        cost_usd=_cost(model, usage),
        blocks=len(rep.blocks),
        warnings=len(rep.findings) - len(rep.blocks),
        findings=[asdict(f) for f in rep.findings],
        text=text,
    )


def summarize(results: list[Result]) -> str:
    rows = [
        f"{'task':22} {'model':34} {'lat':>5} {'in':>6} {'out':>5} {'cost$':>9} {'blk':>3} {'warn':>4}",
        "-" * 94,
    ]
    for r in results:
        cost = f"{r.cost_usd:.5f}" if r.cost_usd is not None else "   n/a"
        rows.append(
            f"{r.task:22.22} {r.model:34.34} {r.latency_s:5.2f} {r.input_tokens:6} "
            f"{r.output_tokens:5} {cost:>9} {r.blocks:3} {r.warnings:4}"
        )
    return "\n".join(rows)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task", help="a single task id from tasks.json")
    p.add_argument(
        "--suite", action="store_true", help="every task against every priced model"
    )
    p.add_argument(
        "--models", help="comma-separated model ids (default: all in pricing.json)"
    )
    p.add_argument("--max-tokens", type=int, default=900)
    p.add_argument("--temperature", type=float, default=0.6)
    p.add_argument("--region", default="us-east-1")
    p.add_argument(
        "--tasks", help="tasks JSON (default: $EVAL_TASKS or dropbox/eval_tasks.json)"
    )
    p.add_argument("--rules", help="canon rules JSON (default: $CANON_RULES)")
    p.add_argument(
        "--save",
        action="store_true",
        help="write prose + JSON under dropbox_archive/eval/",
    )
    args = p.parse_args(argv)

    tasks = load_tasks(args.tasks)
    rules = rubric.load_rules(args.rules)
    if args.task:
        tasks = [t for t in tasks if t["id"] == args.task]
        if not tasks:
            p.error(f"unknown task '{args.task}'")
    elif not args.suite:
        p.error("choose --task <id> or --suite")
    models = args.models.split(",") if args.models else list(PRICING)

    client = boto3.client("bedrock-runtime", region_name=args.region)
    results: list[Result] = []
    for task in tasks:
        for model in models:
            try:
                results.append(
                    run_one(
                        client, model, task, rules, args.max_tokens, args.temperature
                    )
                )
                print(f"ok   {task['id']:22.22} {model}")
            except Exception as exc:  # noqa: BLE001 - record and continue the matrix
                print(
                    f"FAIL {task['id']:22.22} {model}: {str(exc).splitlines()[0][:120]}"
                )

    print("\n" + summarize(results))
    blocked = [r for r in results if r.blocks]
    if blocked:
        print(f"\n{len(blocked)} run(s) tripped a canon block:")
        for r in blocked:
            for f in r.findings:
                if f["severity"] == "block":
                    print(f"  {r.model} / {r.task}: {f['detail']}")

    if args.save:
        REPORTS.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        (REPORTS / f"run-{stamp}.json").write_text(
            json.dumps([asdict(r) for r in results], indent=2)
        )
        for r in results:
            (
                REPORTS
                / f"{r.task}__{r.model.replace(':', '_').replace('.', '_')}__{stamp}.md"
            ).write_text(
                f"# {r.task} / {r.model}\n\nblocks={r.blocks} warnings={r.warnings} "
                f"cost=${r.cost_usd} in={r.input_tokens} out={r.output_tokens} latency={r.latency_s}s\n\n---\n\n{r.text}\n"
            )
        print(f"\nsaved to {REPORTS}")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
