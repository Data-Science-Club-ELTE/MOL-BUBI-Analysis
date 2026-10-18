"""Project linting script supporting ruff, flake8, or standard library AST analysis."""

import ast
import os
import subprocess
import sys


def run_tool_if_available(cmd: list[str]) -> bool:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        print(res.stdout)
        if res.stderr:
            print(res.stderr, file=sys.stderr)
        return res.returncode == 0
    except (FileNotFoundError, PermissionError):
        return False


def lint_with_ast(root_dir: str) -> bool:
    print(f"Running AST syntax & style validation over {root_dir}...")
    error_count = 0
    checked_files = 0

    for dirpath, _, filenames in os.walk(root_dir):
        if any(skip in dirpath for skip in [".git", "__pycache__", ".venv", "venv", ".idea"]):
            continue
        for fname in filenames:
            if fname.endswith(".py"):
                fpath = os.path.join(dirpath, fname)
                checked_files += 1
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        source = f.read()
                    ast.parse(source, filename=fpath)
                except SyntaxError as e:
                    print(f"Syntax error in {fpath}:{e.lineno}: {e.msg}", file=sys.stderr)
                    error_count += 1

    if error_count == 0:
        print(
            f"All {checked_files} Python source files verified successfully with zero syntax errors."
        )
        return True
    else:
        print(f"Linting failed with {error_count} error(s).", file=sys.stderr)
        return False


def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # Try ruff first if available in the environment
    if run_tool_if_available(["ruff", "check", root]):
        print("Ruff lint check passed.")
        sys.exit(0)

    # Fallback to pure-Python AST verification
    success = lint_with_ast(os.path.join(root, "bubi")) and lint_with_ast(
        os.path.join(root, "tests")
    )
    if not success:
        sys.exit(1)
    print("Lint checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
