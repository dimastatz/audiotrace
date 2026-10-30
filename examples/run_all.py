"""Run every example against the bundled call (the CI `examples` job)."""

import analyze_one_call
import compare_two_calls
import custom_pricing
import gate_directory

if __name__ == "__main__":
    analyze_one_call.main()
    compare_two_calls.main()
    custom_pricing.main()
    if not gate_directory.main().passed:
        raise SystemExit("re-analyzing the same call should pass the gate")
    print("All examples ran.")
