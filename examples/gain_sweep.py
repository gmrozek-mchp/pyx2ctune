"""Automated gain sweep example.

Iterates over a range of Kp values (with fixed Ki), captures a step
response at each point, computes metrics, and plots a summary.

Usage:
    python gain_sweep.py --port /dev/tty.usbmodem1 --elf firmware.elf --params parameters.json
"""

import argparse
import json
import sys
import time

from pyx2ctune import TuningSession
from pyx2ctune.analysis import StepMetrics, compute_metrics
from pyx2ctune.plotting import plot_gain_sweep, plot_step_response


def main():
    parser = argparse.ArgumentParser(description="Automated Kp gain sweep")
    parser.add_argument("--port", required=True, help="Serial port")
    parser.add_argument("--elf", required=True, help="Path to firmware ELF file")
    parser.add_argument("--params", required=True, help="Path to parameters.json")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate")
    parser.add_argument("--ki", type=float, required=True, help="Fixed Ki value (V/A/s)")
    parser.add_argument(
        "--kp-range", nargs=3, type=float, metavar=("START", "STOP", "STEP"),
        default=[0.5, 8.0, 0.5],
        help="Kp sweep range: start stop step (V/A)",
    )
    parser.add_argument("--amplitude", type=int, default=500, help="Perturbation amplitude")
    parser.add_argument("--halfperiod", type=int, default=100, help="Perturbation half-period")
    parser.add_argument("--axis", default="q", choices=["q", "d"])
    parser.add_argument("--output", default=None, help="Save results to JSON file")
    parser.add_argument("--plot-each", action="store_true", help="Plot each step response individually")
    args = parser.parse_args()

    kp_start, kp_stop, kp_step = args.kp_range
    kp_values = []
    kp = kp_start
    while kp <= kp_stop + 1e-9:
        kp_values.append(round(kp, 6))
        kp += kp_step

    print(f"Gain sweep: {len(kp_values)} Kp values from {kp_values[0]} to {kp_values[-1]} V/A")
    print(f"Fixed Ki = {args.ki} V/A/s")

    session = TuningSession(
        port=args.port,
        elf_file=args.elf,
        baud_rate=args.baud,
        parameters_json=args.params,
    )

    results = []

    try:
        session.test_harness.enter_current_test_mode()
        session.capture.configure_current_loop(axis=args.axis)

        for i, kp in enumerate(kp_values):
            print(f"\n[{i+1}/{len(kp_values)}] Kp={kp:.4f} V/A, Ki={args.ki:.2f} V/A/s")

            session.current.set_gains(kp=kp, ki=args.ki)
            time.sleep(0.1)

            session.current.setup_step_test(
                axis=args.axis,
                amplitude=args.amplitude,
                halfperiod=args.halfperiod,
            )
            time.sleep(0.2)

            response = session.capture.capture_frame(timeout=10.0)
            metrics = compute_metrics(response)

            print(f"  OS={metrics.overshoot:.1%}  Tr={metrics.rise_time_us:.0f}\u00b5s  "
                  f"Ts={metrics.settling_time_us:.0f}\u00b5s  SSE={metrics.steady_state_error:.3f}")

            result = {
                "kp": kp,
                "ki": args.ki,
                "overshoot": metrics.overshoot,
                "rise_time_us": metrics.rise_time_us,
                "settling_time_us": metrics.settling_time_us,
                "steady_state_error": metrics.steady_state_error,
                "n_steps": metrics.n_steps,
            }
            results.append(result)

            if args.plot_each:
                plot_step_response(response, metrics, show=True,
                                   title=f"Kp={kp:.4f} V/A, Ki={args.ki:.2f} V/A/s")

            session.current.stop_perturbation()
            time.sleep(0.1)

    finally:
        session.current.stop_perturbation()
        session.test_harness.exit_test_mode()
        session.disconnect()

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.output}")

    print("\n--- Sweep Summary ---")
    print(f"{'Kp':>8s}  {'OS':>6s}  {'Tr(us)':>8s}  {'Ts(us)':>8s}  {'SSE':>6s}")
    for r in results:
        print(f"{r['kp']:8.4f}  {r['overshoot']:5.1%}  {r['rise_time_us']:8.0f}  "
              f"{r['settling_time_us']:8.0f}  {r['steady_state_error']:6.3f}")

    plot_gain_sweep(results, x_key="kp", show=True,
                    title=f"Kp Sweep (Ki={args.ki:.2f} V/A/s)")


if __name__ == "__main__":
    main()
