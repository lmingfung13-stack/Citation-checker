import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.reference_service import split_reference_items


def run_case(name: str, text: str, expected_count: int):
    try:
        items = split_reference_items(text)
    except Exception as e:
        return {
            "name": name,
            "passed": False,
            "reason": f"exception: {e.__class__.__name__}: {e}",
        }

    actual = len(items)
    if actual != expected_count:
        return {
            "name": name,
            "passed": False,
            "reason": f"expected_count={expected_count}, actual_count={actual}, items={items}",
        }

    return {
        "name": name,
        "passed": True,
        "reason": "",
    }


def main():
    cases = [
        {
            "name": "Case1: blank-line split should be 3",
            "input": "A\u6587\u737b\nB\u6587\u737b\n\nC\u6587\u737b",
            "expected_count": 3,
        },
        {
            "name": "Case2: consecutive blank lines still 3",
            "input": "A\n\n\nB\n\nC",
            "expected_count": 3,
        },
        {
            "name": "Case3: multiline single item without blank line",
            "input": "Hummel, K., & Schlick, C. (2016).\nThe relationship between sustainability performance and sustainability disclosure.\nJournal of Accounting and Public Policy, 35, 455\u2013476.",
            "expected_count": 1,
        },
    ]

    results = [run_case(c["name"], c["input"], c["expected_count"]) for c in cases]
    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed

    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"[{status}] {r['name']}")

    print("---")
    print(f"Total: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        print("Failure details:")
        for r in results:
            if not r["passed"]:
                print(f"- {r['name']}: {r['reason']}")


if __name__ == "__main__":
    main()
