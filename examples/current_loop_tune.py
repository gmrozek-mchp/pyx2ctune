"""End-to-end current loop tuning example.

Connects to the target, enters current test mode, sets PI gains,
captures a step response, analyzes metrics, and plots the result.

Usage:
    python current_loop_tune.py --port /dev/tty.usbmodem1 --elf firmware.elf

Before running:
    1. Build and flash the MCAF firmware with X2Cscope enabled
    2. Connect the board via USB/UART
    3. Update the paths below or pass via command-line arguments
"""

import argparse
import sys

from pyx2ctune import TuningSession
from pyx2ctune.analysis import compute_metrics
from pyx2ctune.plotting import plot_step_response


def main():
    parser = argparse.ArgumentParser(description="MCAF current loop tuning")
    parser.add_argument("--port", required=True, help="Serial port (e.g. /dev/tty.usbmodem1, COM3)")
    parser.add_argument("--elf", required=True, help="Path to firmware ELF file")
    parser.add_argument("--params", default=None, help="Path to motorBench parameters.json")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument("--kp", type=float, default=None, help="Proportional gain (V/A)")
    parser.add_argument("--ki", type=float, default=None, help="Integral gain (V/A/s)")
    parser.add_argument("--amplitude", type=float, default=0.5, help="Perturbation amplitude (A)")
    parser.add_argument("--halfperiod", type=float, default=5.0, help="Perturbation half-period (ms)")
    parser.add_argument("--axis", default="q", choices=["q", "d"], help="Current axis to tune")
    args = parser.parse_args()

    print(f"Connecting to {args.port} at {args.baud} baud...")
    session = TuningSession(
        port=args.port,
        elf_file=args.elf,
        baud_rate=args.baud,
        parameters_json=args.params,
    )

    try:
        print("Entering current test mode...")
        session.test_harness.enter_current_test_mode()

        if args.kp is not None and args.ki is not None:
            if args.params is None:
                print(f"Setting gains in counts: Kp={args.kp}, Ki={args.ki}")
                session.current.set_gains(args.kp, args.ki, units="counts")
            else:
                print(f"Setting gains: Kp={args.kp} V/A, Ki={args.ki} V/A/s")
                session.current.set_gains(args.kp, args.ki, units="engineering")

        current_gains = session.current.get_gains(args.axis)
        print(f"Current gains: Kp={current_gains.kp:.4f} (counts={current_gains.kp_counts}, Q{current_gains.kp_shift})")
        print(f"               Ki={current_gains.ki:.2f} (counts={current_gains.ki_counts}, Q{current_gains.ki_shift})")

        print(f"Configuring scope for {args.axis}-axis current loop...")
        session.capture.configure_current_loop(axis=args.axis)

        print(f"Starting perturbation: amplitude={args.amplitude:.3f} A, halfperiod={args.halfperiod:.2f} ms")
        session.current.setup_step_test(
            axis=args.axis,
            amplitude=args.amplitude,
            halfperiod=args.halfperiod,
            units="engineering",
        )

        print("Capturing step response...")
        response = session.capture.capture_frame(timeout=10.0)
        print(f"Captured {len(response.measured)} samples ({response.metadata.get('capture_duration_ms', 0):.1f} ms)")

        metrics = compute_metrics(response)
        print(f"\nStep Response Metrics ({metrics.n_steps} steps detected):")
        print(f"  Overshoot:          {metrics.overshoot:.1%}")
        print(f"  Rise time:          {metrics.rise_time_us:.0f} \u00b5s")
        print(f"  Settling time:      {metrics.settling_time_us:.0f} \u00b5s")
        print(f"  Steady-state error: {metrics.steady_state_error:.3f}")

        plot_step_response(response, metrics, show=True)

    finally:
        print("\nCleaning up...")
        session.current.stop_perturbation()
        session.test_harness.exit_test_mode()
        session.disconnect()
        print("Done.")


if __name__ == "__main__":
    main()
