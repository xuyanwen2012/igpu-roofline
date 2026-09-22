"""igpu-roofline command line: build, run, report."""
import argparse
import sys

from . import paths


def _load_overrides(path: str | None) -> dict:
    if not path:
        return {}
    import yaml
    with open(path) as f:
        return yaml.safe_load(f) or {}


def cmd_build(args):
    from .build import build
    build(args.jobs)


def cmd_run(args):
    from .device import AdbDevice, list_adb_devices
    from .session import Session
    from .stages import run_plan

    if not args.device:
        devices = list_adb_devices()
        if not devices:
            print("No adb devices. Connect a device with USB debugging enabled.")
        for d in devices:
            print(f"{d['serial']:24s} {d['model']:20s} {d['product']}")
        print("\nRun: igpu-roofline run --device <serial> [--plan quick|standard|gold]")
        return
    if not paths.RUNNER.exists() or not paths.SHADER_MANIFEST.exists():
        sys.exit("Not built yet: run `igpu-roofline build` first.")
    device = AdbDevice(args.device, _load_overrides(args.overrides))
    session = Session(device, paths.results_root(args.results), plan=args.plan)
    print(f"Plan '{args.plan}' on {args.device}; results in {session.out}", flush=True)
    run_plan(session, args.plan)
    if not args.no_report:
        from .report import analyze
        analyze(session.out)
        print(f"Report: {session.out / 'report' / 'REPORT.md'}")


def cmd_report(args):
    from .report import analyze, analyze_all
    root = paths.results_root(args.results)
    if args.device:
        analyze(root / args.device)
    else:
        analyze_all(root)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="igpu-roofline", description="Vulkan roofline microbenchmarks for mobile and integrated GPUs.")
    ap.add_argument("--results", help="results directory (default: $IGPU_ROOFLINE_RESULTS or ~/igpu-roofline-results)")
    sub = ap.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="compile shaders (with SPIR-V ledger checks) and the Android runner")
    b.add_argument("-j", "--jobs", type=int, default=8)
    b.set_defaults(func=cmd_build)

    r = sub.add_parser("run", help="measure a device (resumable); without --device, list devices")
    r.add_argument("--device", help="adb serial")
    r.add_argument("--plan", choices=["quick", "standard", "gold"], default="quick",
                   help="quick ~10 min; standard ~3 h (1 sustained batch); gold ~7 h (3 sustained batches)")
    r.add_argument("--overrides", help="optional device override YAML (see docs/HOW-TO-RUN.md)")
    r.add_argument("--no-report", action="store_true", help="skip report generation at the end")
    r.set_defaults(func=cmd_run)

    p = sub.add_parser("report", help="(re)generate reports from existing results")
    p.add_argument("--device", help="only this serial")
    p.set_defaults(func=cmd_report)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
