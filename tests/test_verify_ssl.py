"""`verify_ssl` turns off outbound TLS verification for every httpx client the gateway builds."""
import ast
import os
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.settings import SCHEMA, verify_ssl  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def client_calls(path):
    """Every httpx.Client/AsyncClient constructor in one module, as keyword maps."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr in ("Client", "AsyncClient")
                and isinstance(func.value, ast.Name) and func.value.id == "httpx"):
            found.append({keyword.arg: ast.unparse(keyword.value) for keyword in node.keywords
                          if keyword.arg})
    return found


class VerifySslTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ, {})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("CODEBUDDY2API_VERIFY_SSL", None)

    def test_defaults_to_verifying(self):
        self.assertIs(verify_ssl(), True)
        self.assertIs(SCHEMA["verify_ssl"]["default"], True)

    def test_false_values_disable_and_others_keep_verifying(self):
        for value in ("false", "FALSE", "0", "no", "off", " off "):
            with self.subTest(value=value):
                os.environ["CODEBUDDY2API_VERIFY_SSL"] = value
                self.assertIs(verify_ssl(), False)
        for value in ("true", "1", "yes", "on", ""):
            with self.subTest(value=value):
                os.environ["CODEBUDDY2API_VERIFY_SSL"] = value
                self.assertIs(verify_ssl(), True)

    def test_setting_locks_and_restarts_like_the_other_transport_knobs(self):
        spec = SCHEMA["verify_ssl"]
        self.assertEqual(spec["type"], "boolean")
        self.assertEqual(spec["mode"], "restart")
        self.assertEqual(spec["env"], "CODEBUDDY2API_VERIFY_SSL")

    def test_httpx_honours_a_false_result(self):
        """The value must reach httpx as a usable `verify=` argument."""
        import httpx
        with patch.dict(os.environ, {"CODEBUDDY2API_VERIFY_SSL": "false"}):
            client = httpx.Client(verify=verify_ssl())
        try:
            context = client._transport._pool._ssl_context
            import ssl
            self.assertFalse(context.check_hostname)
            self.assertEqual(context.verify_mode, ssl.CERT_NONE)
        finally:
            client.close()


class EveryClientFollowsThePolicyTests(unittest.TestCase):
    """A new outbound client that forgets `verify=` would silently keep verifying."""

    def test_application_clients_pass_the_setting(self):
        modules = [ROOT / "converter.py", *(ROOT / "app").glob("*.py")]
        offenders = []
        for path in modules:
            for keywords in client_calls(path):
                if keywords.get("verify") != "verify_ssl()":
                    offenders.append(f"{path.name}: {keywords}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
