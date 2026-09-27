#!/usr/bin/env python3
"""Flip a local LATEST pointer after verifying a separate approval record."""

from __future__ import annotations
import argparse

from lib.promotion_evaluator import FileStore, promote_approved_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-uri", required=True)
    parser.add_argument("--approval-uri", required=True)
    parser.add_argument("--contract-uri", required=True)
    parser.add_argument("--latest-uri", required=True)
    args = parser.parse_args()
    promote_approved_report(
        FileStore(),
        report_uri=args.report_uri,
        approval_uri=args.approval_uri,
        contract_uri=args.contract_uri,
        latest_uri=args.latest_uri,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
