"""igpu-roofline command line: build, run, report."""

import argparse
import signal
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

    build(
        args.jobs,
        host=args.host,
        shaders_too=not args.no_shaders,
        vulkan_include=args.vulkan_include,
    )


def cmd_run(args):
    from .planning import load_replay
    from .stages import run_plan

    replay = load_replay(args.replay) if args.replay else None
    session = _session(args)
    if session is None:
        return
    try:
        run_plan(
            session,
            args.plan,
            families=args.family,
            variants=args.variant,
            stages=args.stage,
            replay=replay,
            sustained=args.sustained,
        )
        _report(session, args)
    finally:
        session.close()


def cmd_sustain(args):
    from .stages import run_sustained

    session = _session(args)
    if session is None:
        raise ValueError("sustain requires --device or --local")
    try:
        run_sustained(
            session,
            roof_keys=args.roof,
            duration=args.duration,
            batches=args.batches,
            cooldown=args.cooldown,
        )
        _report(session, args)
    finally:
        session.close()


def _report(session, args):
    if not args.no_report:
        from .report import analyze
        from .timing import record_timing

        with record_timing(session.out, "stage", "report", plan=args.plan):
            analyze(session.out)
        print(f"Report: {session.out / 'report' / 'REPORT.md'}")


def _session(args):
    from .device import AdbDevice, list_adb_devices
    from .session import Session

    if args.local:
        from .device import LocalDevice

        paths.use_target("host")
        if not paths.RUNNER.exists() or not paths.SHADER_MANIFEST.exists():
            sys.exit(
                "Host runner not built yet: run `igpu-roofline build --host` first."
            )
        device = LocalDevice(args.local_name, _load_overrides(args.overrides))
        session = Session(device, paths.results_root(args.results), plan=args.plan)
        print(
            f"Plan '{args.plan}' on local GPU ({device.serial}); results in {session.out}",
            flush=True,
        )
        return session
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
    return session


def cmd_shapes(args):
    from .device import AdbDevice, LocalDevice
    from .shapes import probe, table

    if args.local:
        paths.use_target("host")
        device = LocalDevice(None)
    elif args.device:
        from .device import list_adb_devices

        if args.device not in [d["serial"] for d in list_adb_devices()]:
            sys.exit(f"{args.device} is not connected (adb devices).")
        device = AdbDevice(args.device)
    else:
        sys.exit("give --device <serial> or --local")
    if not paths.RUNNER.exists():
        sys.exit(
            "Runner not built: run `igpu-roofline build` (or `build --host`) first."
        )
    caps = probe(device, paths.RUNNER)
    print(
        f"{caps['gpu']} (driver {caps['driver_version']}, subgroup {caps['subgroup']}, "
        f"shared {caps['max_shared_bytes']} B)\n"
    )
    print(table(caps))


def cmd_report(args):
    from .report import analyze, analyze_all

    root = paths.results_root(args.results)
    if args.device:
        analyze(root / args.device)
    else:
        analyze_all(root)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="igpu-roofline",
        description="Vulkan roofline microbenchmarks for mobile and integrated GPUs.",
    )
    ap.add_argument(
        "--results",
        help="results directory (default: $IGPU_ROOFLINE_RESULTS or ~/igpu-roofline-results)",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    b = sub.add_parser(
        "build",
        help="compile shaders (with SPIR-V ledger checks) and the Android runner",
    )
    b.add_argument("-j", "--jobs", type=int, default=8)
    b.add_argument(
        "--host",
        action="store_true",
        help="build the runner for this host's GPU instead of Android",
    )
    b.add_argument(
        "--no-shaders",
        action="store_true",
        help="reuse build/shaders (SPIR-V compiled on another machine)",
    )
    b.add_argument(
        "--vulkan-include",
        help="directory with vulkan/vulkan.h when system headers are missing",
    )
    b.set_defaults(func=cmd_build)

    r = sub.add_parser(
        "run", help="measure a device (resumable); without --device, list devices"
    )

    def device_args(parser):
        target = parser.add_mutually_exclusive_group()
        target.add_argument("--device", help="adb serial")
        target.add_argument(
            "--local", action="store_true", help="measure this host's own GPU"
        )
        parser.add_argument("--local-name", help="results folder name for --local")
        parser.add_argument("--overrides", help="optional device override YAML")
        parser.add_argument(
            "--no-report", action="store_true", help="skip report generation"
        )

    device_args(r)
    r.add_argument(
        "--plan",
        choices=["quick", "fast", "standard", "gold"],
        default="quick",
        help="quick: smoke test (~15-30 min); fast: shader-tuning roofs incl. WMMA feed and texture (~35-45 min, estimate); standard ~4 h; gold ~7 h",
    )
    from .stages import SHORT_STAGES

    r.add_argument(
        "--family",
        action="append",
        default=[],
        help="select a family; repeat to select several",
    )
    r.add_argument(
        "--variant",
        action="append",
        default=[],
        help="select an exact shader name; repeatable",
    )
    r.add_argument(
        "--stage",
        action="append",
        default=[],
        choices=[step.__name__ for step in SHORT_STAGES],
        help="select a short-run stage; confirmation follows automatically",
    )
    r.add_argument(
        "--replay",
        help="re-measure best-configurations.json or report/summary.json using the current build",
    )
    sustained = r.add_mutually_exclusive_group()
    sustained.add_argument(
        "--sustain",
        dest="sustained",
        action="store_true",
        default=None,
        help="include this plan's sustained tests, also for focused runs",
    )
    sustained.add_argument(
        "--no-sustain",
        dest="sustained",
        action="store_false",
        help="omit sustained tests",
    )
    r.set_defaults(func=cmd_run)

    su = sub.add_parser(
        "sustain",
        help="run sustained tests of current confirmed roofs without discovery",
    )
    device_args(su)
    su.add_argument(
        "--roof",
        action="append",
        default=[],
        help="confirmation roof key; repeatable; default all",
    )
    su.add_argument(
        "--duration", type=int, default=300, help="seconds per roof (at least 60)"
    )
    su.add_argument("--batches", type=int, default=1)
    su.add_argument("--cooldown", type=int, default=90, help="seconds before each roof")
    su.set_defaults(func=cmd_sustain, plan="sustain")

    sh = sub.add_parser(
        "shapes",
        help="list the device's cooperative-matrix (WMMA) shapes as a Markdown table",
    )
    sh.add_argument("--device", help="adb serial")
    sh.add_argument("--local", action="store_true", help="this host's own GPU")
    sh.set_defaults(func=cmd_shapes)

    p = sub.add_parser("report", help="(re)generate reports from existing results")
    p.add_argument("--device", help="only this serial")
    p.set_defaults(func=cmd_report)

    args = ap.parse_args(argv)
    if args.command == "run" and args.replay and args.stage:
        ap.error("--replay cannot be combined with --stage; use --family or --variant")
    if args.command == "sustain":
        if not (args.local or args.device):
            ap.error("sustain requires --device or --local")
        if args.duration < 60 or args.batches < 1 or args.cooldown < 0:
            ap.error("sustain requires duration >= 60, batches >= 1 and cooldown >= 0")

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    previous_sigterm = signal.signal(signal.SIGTERM, interrupted)
    try:
        args.func(args)
    except (ValueError, FileNotFoundError) as e:
        ap.error(str(e))
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)


if __name__ == "__main__":
    main()
