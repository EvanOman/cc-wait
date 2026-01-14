#!/usr/bin/env python3
"""Test script for the wait_for_limits hook."""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

HOOK_SCRIPT = Path(__file__).parent / 'wait_for_limits.py'

# Import the hook module for unit testing
sys.path.insert(0, str(HOOK_SCRIPT.parent))
from wait_for_limits import parse_reset_time, extract_wait_seconds


def test_parse_reset_time():
    """Test reset time parsing."""
    print("\n" + "="*50)
    print("Testing parse_reset_time()")

    test_cases = [
        ("Your limit will reset at 7pm", 19, 0),
        ("reset at 3:30pm (America/New_York)", 15, 30),
        ("resets at 14:00", 14, 0),
        ("will reset at 9am", 9, 0),
        ("reset at 12pm", 12, 0),
        ("reset at 12am", 0, 0),
    ]

    passed = 0
    for text, expected_hour, expected_minute in test_cases:
        result = parse_reset_time(text)
        if result:
            actual_hour = result.hour
            actual_minute = result.minute
            if actual_hour == expected_hour and actual_minute == expected_minute:
                print(f"  ✓ '{text}' -> {result.strftime('%H:%M')}")
                passed += 1
            else:
                print(f"  ✗ '{text}' -> {result.strftime('%H:%M')} (expected {expected_hour:02d}:{expected_minute:02d})")
        else:
            print(f"  ✗ '{text}' -> None (expected {expected_hour:02d}:{expected_minute:02d})")

    print(f"\nPassed: {passed}/{len(test_cases)}")
    return passed == len(test_cases)


def test_extract_wait_seconds():
    """Test wait seconds extraction."""
    print("\n" + "="*50)
    print("Testing extract_wait_seconds()")

    test_cases = [
        ("try again in 30 seconds", 30),
        ("wait 5 minutes", 300),
        ("retry after 2 hours", 7200),
        ("retry-after: 60", 60),
        ("in 5:30", 330),
    ]

    passed = 0
    for text, expected in test_cases:
        result = extract_wait_seconds(text)
        if result == expected:
            print(f"  ✓ '{text}' -> {result}s")
            passed += 1
        else:
            print(f"  ✗ '{text}' -> {result}s (expected {expected}s)")

    print(f"\nPassed: {passed}/{len(test_cases)}")
    return passed == len(test_cases)


def test_hook_integration(test_name: str, hook_input: dict, expect_wait: bool):
    """Run the hook with given input."""
    print(f"\n{'='*50}")
    print(f"Test: {test_name}")

    result = subprocess.run(
        ['python3', str(HOOK_SCRIPT)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        timeout=3  # Short timeout
    )

    print(f"  Exit code: {result.returncode}")
    print(f"  Stderr: {result.stderr.strip()[:100]}")

    if expect_wait:
        # Should timeout because it's waiting
        print("  ✗ Expected to timeout (waiting)")
        return False

    try:
        output = json.loads(result.stdout)
        decision = output.get('decision')
        print(f"  Decision: {decision}")
        return decision == 'allow'
    except:
        return False


def main():
    print("Testing wait_for_limits hook")
    print(f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = []

    # Unit tests
    results.append(test_parse_reset_time())
    results.append(test_extract_wait_seconds())

    # Integration tests (non-waiting scenarios)
    try:
        results.append(test_hook_integration(
            "Empty input (no rate limit)",
            {},
            expect_wait=False
        ))

        results.append(test_hook_integration(
            "Normal stop (no rate limit)",
            {"session_id": "test", "stop_reason": "end_turn"},
            expect_wait=False
        ))
    except subprocess.TimeoutExpired:
        print("  ! Unexpected timeout")
        results.append(False)

    # Test rate limit detection (will timeout)
    print(f"\n{'='*50}")
    print("Test: Rate limit with reset time")
    print("(This should detect rate limit and start waiting)")

    try:
        result = subprocess.run(
            ['python3', str(HOOK_SCRIPT)],
            input=json.dumps({
                "message": "Usage limit reached. Your limit will reset at 7pm"
            }),
            capture_output=True,
            text=True,
            timeout=2
        )
        print(f"  ✗ Should have started waiting but didn't")
        print(f"  Stderr: {result.stderr}")
        results.append(False)
    except subprocess.TimeoutExpired:
        print("  ✓ Rate limit detected, hook started waiting (timeout expected)")
        results.append(True)

    # Summary
    print(f"\n{'='*50}")
    print("SUMMARY")
    print(f"Passed: {sum(results)}/{len(results)} tests")
    print("\nTo test in production:")
    print("  1. Run Claude Code from this directory")
    print("  2. Use until you hit rate limits")
    print("  3. Hook will detect reset time and wait automatically")
    print("\nEnable debug: export CC_WAIT_DEBUG=1")

    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
