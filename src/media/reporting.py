#!/usr/bin/env python3

from __future__ import annotations

from typing import Any


def count_actions(
    results: list[dict[str, Any]],
) -> dict[str, int]:
    action_counts: dict[str, int] = {}

    for result in results:
        action = str(result.get("action") or "UNKNOWN")
        action_counts[action] = (
            action_counts.get(action, 0) + 1
        )

    return action_counts


def count_verify_passed(
    results: list[dict[str, Any]],
) -> int:
    return sum(
        1
        for result in results
        if result.get("verify_status") == "OK"
    )


def print_sync_summary(
    results: list[dict[str, Any]],
) -> None:
    action_counts = count_actions(results)

    print("\n" + "=" * 70)
    print("ATTĒLU SINHRONIZĀCIJAS KOPSAVILKUMS")
    print("=" * 70)

    print(
        f"Apstrādāti:       {len(results)}"
    )
    print(
        f"Atjaunināti:      "
        f"{action_counts.get('UPDATED', 0)}"
    )
    print(
        f"Verify passed:    "
        f"{count_verify_passed(results)}"
    )
    print(
        f"Verify failed:    "
        f"{action_counts.get('VERIFY_FAILED', 0)}"
    )
    print(
        f"Dry run SYNC:     "
        f"{action_counts.get('DRY_RUN', 0)}"
    )
    print(
        f"Jau kārtībā:      "
        f"{action_counts.get('SKIP_OK', 0)}"
    )
    print(
        f"Manuāli jāpārbauda: "
        f"{action_counts.get('SKIP_REVIEW', 0)}"
    )
    print(
        f"Kļūdas:           "
        f"{action_counts.get('ERROR', 0)}"
    )


def sync_exit_code(
    results: list[dict[str, Any]],
) -> int:
    action_counts = count_actions(results)

    failed_count = (
        action_counts.get("ERROR", 0)
        + action_counts.get("VERIFY_FAILED", 0)
    )

    return 1 if failed_count else 0
