import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/bootstrap-local.sh"


class BootstrapLocalTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.scripts = self.root / "scripts"
        self.scripts.mkdir()
        self.copy = self.scripts / "bootstrap-local.sh"
        if SCRIPT.exists():
            self.copy.write_bytes(SCRIPT.read_bytes())
            self.copy.chmod(0o755)
        self.log = self.root / "calls.log"
        preflight = self.scripts / "preflight.sh"
        preflight.write_text("#!/bin/sh\nprintf 'preflight %s\\n' \"$*\" >> \"$CALL_LOG\"\n")
        preflight.chmod(0o755)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.write_tool("uname", "case \"$1\" in -s) echo Darwin;; -m) echo arm64;; esac")

    def write_tool(self, name, body):
        tool = self.bin / name
        tool.write_text(f"#!/bin/sh\n{body}\n")
        tool.chmod(0o755)
        return tool

    def invoke(self, *args):
        env = {
            **os.environ,
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "CALL_LOG": str(self.log),
            "FAKE_BIN": str(self.bin),
        }
        return subprocess.run([self.copy, *args], env=env, capture_output=True, text=True)

    def calls(self):
        return self.log.read_text() if self.log.exists() else ""

    def test_default_mode_is_non_mutating_and_runs_non_strict_preflight(self):
        self.write_tool("brew", "echo brew >> \"$CALL_LOG\"")
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), "preflight --phase step-minus-one\n")
        self.assertIn("--install", result.stdout)

    def test_install_uses_homebrew_then_mise_install_lock_and_strict_preflight(self):
        self.write_tool("brew", """echo "brew $*" >> "$CALL_LOG"
if [ "$1 $2" = "install mise" ]; then
  cat > "$FAKE_BIN/mise" <<'EOF'
#!/bin/sh
echo "mise $*" >> "$CALL_LOG"
if [ "$1 $2" = "env --paths" ]; then
  echo "$FAKE_BIN"
fi
EOF
  chmod +x "$FAKE_BIN/mise"
fi""")
        result = self.invoke("--install")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.calls().splitlines(),
            [
                "brew install mise",
                "mise install",
                "mise lock",
                "mise env --paths",
                "preflight --phase step-minus-one --strict",
            ],
        )

    def test_unsupported_platform_refuses_install(self):
        self.write_tool("uname", "case \"$1\" in -s) echo FreeBSD;; -m) echo amd64;; esac")
        result = self.invoke("--install")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("manual", result.stderr.lower())
        self.assertEqual(self.calls(), "")

    def test_unknown_option_exits_two(self):
        self.assertEqual(self.invoke("--bogus").returncode, 2)

    def test_install_failure_stops_before_preflight_and_redacts_output(self):
        marker = "synthetic-token-never-print"
        self.write_tool("mise", f"echo {marker}; echo \"mise $*\" >> \"$CALL_LOG\"; exit 9")
        result = self.invoke("--install")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(marker, result.stdout + result.stderr)
        self.assertEqual(self.calls(), "mise install\n")


if __name__ == "__main__":
    unittest.main()
