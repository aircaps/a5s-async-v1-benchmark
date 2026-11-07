"""Command line: bench prep | verify | run | hyp | score | report | breakdown | speed | speed-report."""
import argparse
import asyncio


def main() -> None:
    parser = argparse.ArgumentParser(prog="bench")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prep", help="build test audio, manifest and references from the official download")
    p.add_argument("dataset")
    p.add_argument("--source", help="folder holding the downloaded dataset (Hugging Face sets: download cache)")

    p = sub.add_parser("verify", help="check prepared audio and references against the published manifest")
    p.add_argument("dataset")
    p.add_argument("--manifest", required=True, help="manifest.jsonl from the Hugging Face dataset repo")

    for name, help_text in [("run", "send recordings to providers and store raw responses"),
                            ("hyp", "convert raw responses to SegLST hypotheses"),
                            ("score", "score hypotheses")]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--providers", required=True, help="comma-separated, see configs/providers.yaml")
        p.add_argument("--datasets", required=True, help="comma-separated")
        if name == "run":
            p.add_argument("--concurrency", type=int, help="override the configured limit")
            p.add_argument("--sample", type=float, default=1.0, help="send only this fraction (every k-th recording)")
        if name == "score":
            p.add_argument("--metric", default="cpwer", choices=["cpwer", "tcpwer", "tcorcwer"])
        if name in ("hyp", "score"):
            p.add_argument("--strict", action="store_true",
                           help="parts of a split file as separate speakers (results/strict/), instead of joined")

    p = sub.add_parser("report", help="print the results table")
    p.add_argument("--metric", default="cpwer")

    p = sub.add_parser("breakdown", help="error rates by number of reference speakers or by overlap")
    p.add_argument("--by", required=True, choices=["speakers", "overlap"])
    p.add_argument("--metric", default="cpwer")
    p.add_argument("--providers", help="comma-separated; default all scored")
    p.add_argument("--datasets", help="comma-separated; default the English main sets: notsofar, ami, chime6")

    p = sub.add_parser("speed", help="end-to-end API speed test, all providers at once (see bench/speed.py)")
    p.add_argument("--providers", required=True, help="comma-separated; each runs in its own process")
    p.add_argument("--tests", default="C,B2", help="comma-separated, of C (latency) and B2 (14 in flight)")
    p.add_argument("--rounds", type=int, help="rounds of B2 (default 3), e.g. 1 for a trial")
    p.add_argument("--sample", type=float, default=1.0, help="every k-th meeting only, for a trial")
    sub.add_parser("speed-report", help="print the speed tables")

    args = parser.parse_args()
    if args.command == "prep":
        from .datasets import prepare
        prepare(args.dataset, args.source)
    elif args.command == "verify":
        from .datasets import verify
        verify(args.dataset, args.manifest)
    elif args.command == "report":
        from .report import table
        print(table(args.metric))
    elif args.command == "speed":
        from .speed import run
        asyncio.run(run(args.providers.split(","), args.tests.split(","), args.rounds, args.sample))
    elif args.command == "speed-report":
        from .speed import report
        print(report())
    elif args.command == "breakdown":
        from .breakdown import table
        print(table(args.by, args.metric, args.providers and args.providers.split(","),
                    args.datasets and args.datasets.split(",")))
    else:
        providers, datasets = args.providers.split(","), args.datasets.split(",")
        if args.command == "run":
            from .run import run
            asyncio.run(run(providers, datasets, args.concurrency, args.sample))
        elif args.command == "hyp":
            from .hyp import build
            for p in providers:
                for d in datasets:
                    print(p, d, build(p, d, args.strict), "segments")
        else:
            from .score import score
            for p in providers:
                for d in datasets:
                    s = score(p, d, args.metric, args.strict)
                    print(f"{p} {d} {args.metric} {100 * s['error_rate']:.2f}% ({len(s['failed'])} failed)")


if __name__ == "__main__":
    main()
