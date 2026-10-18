#!/usr/bin/env python3
"""Exercise the Android APK workflow step without contacting GitHub."""

import subprocess
import tempfile
import textwrap
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/update-packages.yml"


def apk_step():
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    start = lines.index("      - name: Publish the Android APK")
    run = lines.index("        run: |", start) + 1
    end = next(i for i in range(run, len(lines)) if lines[i].startswith("      - name:"))
    return textwrap.dedent("\n".join(lines[run:end]))


def check_download_failure():
    mock_gh = """
gh() {
  case "$*" in
    'release list '*) printf '%s\\n' 'v1.2.3' ;;
    'release download '*) echo 'simulated download failure' >&2; return 1 ;;
    'release view '*) printf '%s\\n' 'nomercy-v1.2.3.apk' ;;
    *) echo "unexpected gh call: $*" >&2; return 2 ;;
  esac
}
    """
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "apk-step.sh"
        script.write_bytes((mock_gh + apk_step()).encode("utf-8"))
        result = subprocess.run(
            ["bash", "apk-step.sh"],
            cwd=directory,
            text=True,
            capture_output=True,
        )
        if result.returncode == 0:
            print("FAIL: tagged APK download failure did not fail the build")
            print(result.stdout, end="")
            print(result.stderr, end="")
            return False
        if "Could not download the APK from v1.2.3" not in result.stdout:
            print("FAIL: did not reach the tagged APK download failure path")
            print(result.stdout, end="")
            print(result.stderr, end="")
            return False
        if (Path(directory) / "website/android/nomercy.apk").exists():
            print("FAIL: failed download produced android/nomercy.apk")
            return False
        print("ok: tagged APK download failure stops the build before deploy and tracker update")
        return True


if __name__ == "__main__":
    raise SystemExit(0 if check_download_failure() else 1)
