import sys
import subprocess
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.reference_service import split_reference_items


def _preview_item(text: str, limit: int = 120) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def _get_git_commit() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or None
    except Exception:
        return None


def run_case(name: str, raw_text: str, expected_count: int) -> dict:
    try:
        items = split_reference_items(raw_text)
    except Exception as e:
        return {
            "name": name,
            "input": raw_text,
            "expected_count": expected_count,
            "actual_count": 0,
            "passed": False,
            "reason": f"exception: {e.__class__.__name__}: {e}",
            "error": f"{e.__class__.__name__}: {e}",
            "items": [],
        }

    if any((item or "").strip() == "" for item in items):
        return {
            "name": name,
            "input": raw_text,
            "expected_count": expected_count,
            "actual_count": len(items),
            "passed": False,
            "reason": "empty_item_detected",
            "error": None,
            "items": items,
        }

    if len(items) != expected_count:
        return {
            "name": name,
            "input": raw_text,
            "expected_count": expected_count,
            "actual_count": len(items),
            "passed": False,
            "reason": f"expected_count={expected_count}, actual_count={len(items)}",
            "error": None,
            "items": items,
        }

    return {
        "name": name,
        "input": raw_text,
        "expected_count": expected_count,
        "actual_count": len(items),
        "passed": True,
        "reason": "",
        "error": None,
        "items": items,
    }


def write_markdown_report(results: list[dict], report_path: Path):
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    pass_rate = (passed / total * 100.0) if total else 0.0
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    commit = _get_git_commit()

    lines: list[str] = []
    lines.append("# Reference Regression Test Report")
    lines.append("")
    lines.append(f"- Generated at (ISO): {timestamp}")
    if commit:
        lines.append(f"- Git commit: `{commit}`")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total cases: {total}")
    lines.append(f"- Passed: {passed}")
    lines.append(f"- Failed: {failed}")
    lines.append(f"- Pass rate: {pass_rate:.2f}%")
    lines.append("")

    lines.append("## Failures")
    lines.append("")
    failures = [r for r in results if not r["passed"]]
    if not failures:
        lines.append("None")
        lines.append("")
    else:
        for r in failures:
            lines.append(f"### {r['name']}")
            lines.append("")
            lines.append("Expected:")
            lines.append(f"- expected_count: {r['expected_count']}")
            lines.append("")
            lines.append("Actual:")
            lines.append(f"- actual_count: {r['actual_count']}")
            lines.append("- items_preview:")
            if r["items"]:
                for idx, item in enumerate(r["items"], start=1):
                    lines.append(f"  {idx}. {_preview_item(item)}")
            else:
                lines.append("  1. (none)")
            lines.append("")
            if r.get("error"):
                lines.append(f"Error: {r['error']}")
            else:
                lines.append("Error: None")
            lines.append("")
            lines.append("Input:")
            lines.append("```text")
            lines.append(r["input"])
            lines.append("```")
            lines.append("")

    lines.append("## Passed Cases")
    lines.append("")
    for r in results:
        if r["passed"]:
            lines.append(f"- {r['name']}")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main():
    cases = [
        {
            "name": "Case01 blank-line split 3",
            "input": "A\u6587\u737b\nB\u6587\u737b\n\nC\u6587\u737b",
            "expected_count": 3,
        },
        {
            "name": "Case02 consecutive blanks still 3",
            "input": "A\n\n\nB\n\nC",
            "expected_count": 3,
        },
        {
            "name": "Case03 multiline single item no blank",
            "input": "Hummel, K., & Schlick, C. (2016).\nThe relationship between sustainability performance and sustainability disclosure.\nJournal of Accounting and Public Policy, 35, 455\u2013476.",
            "expected_count": 1,
        },
        {
            "name": "Case04 blank-line + multiline mixed",
            "input": "Aaa, A. (2019). First line...\nline2...\n\nBbb, B. (2020). First line...\nline2...\n\nCcc, C. (2018). First line...",
            "expected_count": 3,
        },
        {
            "name": "Case05 leading/trailing blank lines",
            "input": "\n\nAaa, A. (2019). ...\n\nBbb, B. (2020). ...\n\n",
            "expected_count": 2,
        },
        {
            "name": "Case06 no blank, year heuristic 3",
            "input": "Aaa, A. (2019). ... Ccc.\nBbb, B. (2020). ... Ddd.\nEee, E. (2018). ... Fff.",
            "expected_count": 3,
        },
        {
            "name": "Case07 missing year still 1",
            "input": "Unknown author. Title without year. Journal, 1, 1-2.",
            "expected_count": 1,
        },
        {
            "name": "Case08 year suffix still 1",
            "input": "Aaa, A. (2020a). Title. Journal, 1, 1-2.",
            "expected_count": 1,
        },
        {
            "name": "Case09 organization author still 1",
            "input": "World Health Organization. (2020). Title. URL",
            "expected_count": 1,
        },
        {
            "name": "Case10 surname with prefix still 1",
            "input": "van der Waal, M. (2021). Title. Journal, 1, 1-2.",
            "expected_count": 1,
        },
        {
            "name": "Case11 one-line two refs by year heuristic",
            "input": "Aaa, A. (2019). T1. Bbb, B. (2020). T2.",
            "expected_count": 2,
        },
        {
            "name": "Case12 fullwidth punctuation and spacing",
            "input": "Hummel\uff0c K. & Schlick\uff0c C. (2016).   Title ...",
            "expected_count": 1,
        },
    ]

    results = [run_case(c["name"], c["input"], c["expected_count"]) for c in cases]
    pass_count = sum(1 for r in results if r["passed"])
    fail_count = len(results) - pass_count

    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"[{status}] {r['name']}")

    print("---")
    print(f"Total: {len(results)}")
    print(f"PASS: {pass_count}")
    print(f"FAIL: {fail_count}")

    if fail_count:
        print("Failure details:")
        for r in results:
            if r["passed"]:
                continue
            print(f"- {r['name']}: {r['reason']}")
            for idx, item in enumerate(r.get("items", []), start=1):
                print(f"  {idx}. {_preview_item(item)}")

    report_path = PROJECT_ROOT / "test_report.md"
    write_markdown_report(results, report_path)
    print(f"Report written: {report_path}")


if __name__ == "__main__":
    main()
