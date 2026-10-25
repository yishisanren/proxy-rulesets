import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import qx2loon  # noqa: E402

HARNESS = ROOT / "tests" / "loon_harness.js"
SCRIPTS = ROOT / "loon" / "scripts"
HELLOBIKE_STATIC_KEY = "0199bec97dfa5e0d"
HELLOBIKE_API = "https://api.hellobike.com/api?homepage.startup.popupWindow"


class ConverterTests(unittest.TestCase):
    def test_filter_lines(self):
        self.assertEqual(qx2loon.convert_rule("host, a.example.com, reject"), "DOMAIN,a.example.com,REJECT")
        self.assertEqual(qx2loon.convert_rule("host-suffix, example.com, direct"), "DOMAIN-SUFFIX,example.com,DIRECT")
        self.assertEqual(qx2loon.convert_rule("ip-cidr, 1.2.3.4/32, reject"), "IP-CIDR,1.2.3.4/32,REJECT,no-resolve")
        self.assertEqual(qx2loon.convert_rule("ip6-cidr, 2400::1/128, reject"), "IP-CIDR6,2400::1/128,REJECT,no-resolve")
        self.assertEqual(
            qx2loon.convert_rule("host-wildcard, mquic-*.meituan.com, reject"),
            "AND,((DOMAIN-KEYWORD,mquic-),(DOMAIN-SUFFIX,meituan.com)),REJECT",
        )

    def test_unknown_input_fails_loudly(self):
        for line in (
            "host-wildcard, a?b.example.com, reject",
            "user-agent, foo*, reject",
            "host, a.example.com, my-policy",
        ):
            with self.assertRaises(qx2loon.ConvertError, msg=line):
                qx2loon.convert_rule(line)
        with self.assertRaises(qx2loon.ConvertError):
            qx2loon.parse_snippet("^https://a\\.com url response-body foo response-body bar")

    def test_rewrite_and_script_lines(self):
        snippet = qx2loon.parse_snippet(
            "#!name = Demo\n"
            "^https://a\\.com/x url reject-200\n"
            "^https://a\\.com/y url 302 https://b.com/\n"
            "^https://a\\.com/z url script-response-body https://e.com/s.js\n"
            "^https://a\\.com/q url script-request-body https://e.com/s.js\n"
            "^https://a\\.com/e url script-echo-response https://e.com/s.js\n"
            "hostname = a.com, b.com\n"
        )
        plugin = qx2loon.render_plugin({"id": "demo", "snippet": "https://e.com/demo.snippet"}, snippet)
        base = qx2loon.SCRIPT_URL_BASE
        self.assertIn("^https://a\\.com/x reject-200", plugin)
        self.assertIn("^https://a\\.com/y 302 https://b.com/", plugin)
        self.assertIn(f"http-response ^https://a\\.com/z script-path={base}s.js, requires-body=true, tag=demo-s-1", plugin)
        self.assertIn(f"http-request ^https://a\\.com/q script-path={base}s.js, requires-body=true, tag=demo-s-2", plugin)
        self.assertIn(f"http-request ^https://a\\.com/e script-path={base}s.js, tag=demo-s-3", plugin)
        self.assertIn("[MITM]\nhostname = a.com, b.com", plugin)

        skipping = {"id": "demo", "snippet": "x", "skip_request_body_scripts": ["s.js"]}
        self.assertNotIn("^https://a\\.com/q ", qx2loon.render_plugin(skipping, snippet))


class GeneratedPluginTests(unittest.TestCase):
    def test_plugins_reference_only_mirrored_scripts(self):
        sources = json.loads((ROOT / "loon" / "sources.json").read_text(encoding="utf-8"))["plugins"]
        for source in sources:
            plugin = (ROOT / "loon" / f"{source['id']}.plugin").read_text(encoding="utf-8")
            self.assertRegex(plugin, r"^#!name = .+")
            self.assertIn("[MITM]\nhostname = ", plugin)
            paths = re.findall(r"script-path=(\S+?),", plugin)
            self.assertTrue(paths, source["id"])
            for url in paths:
                self.assertTrue(url.startswith(qx2loon.SCRIPT_URL_BASE), url)
                self.assertTrue((SCRIPTS / url[len(qx2loon.SCRIPT_URL_BASE):]).is_file(), url)
            tags = re.findall(r"tag=(\S+)", plugin)
            self.assertEqual(len(tags), len(set(tags)))


@unittest.skipUnless(shutil.which("node"), "node is required to run the Loon script harness")
class LoonRuntimeTests(unittest.TestCase):
    def run_script(self, name, case):
        proc = subprocess.run(
            ["node", str(HARNESS), str(SCRIPTS / name)],
            input=json.dumps(case), capture_output=True, text=True, check=True,
        )
        result = json.loads(proc.stdout)
        self.assertEqual(result["doneCalls"], 1, "script must call $done exactly once")
        self.assertFalse(result["removeCalled"], "$persistentStore.remove() wipes every key")
        return result

    def test_meituan_hides_tabs(self):
        body = {"data": {"resource": {"tabArea": [
            {"tabName": "homepage"}, {"tabName": "video"}, {"tabName": "xiaotuan"}, {"tabName": "mine"},
        ]}}}
        result = self.run_script("MT.js", {
            "request": {"url": "https://apimobile.meituan.com/aggroup/indexTab", "method": "GET", "headers": {}},
            "response": {"status": 200, "headers": {}, "body": json.dumps(body)},
        })
        tabs = [t["tabName"] for t in json.loads(result["done"]["body"])["data"]["resource"]["tabArea"]]
        self.assertEqual(tabs, ["homepage", "mine"])

    def test_meituan_leaves_unparseable_body_alone(self):
        result = self.run_script("MT.js", {
            "request": {"url": "https://apimobile.meituan.com/aggroup/indexTab", "method": "GET", "headers": {}},
            "response": {"status": 200, "headers": {}, "body": "<html>"},
        })
        self.assertEqual(result["done"], {})

    def test_hellobike_echo_returns_loon_mock_response(self):
        url = ("https://resource.51downapp.cn/f414fbc17c411b4e986ba8891c738a49.json"
               "?md5=e5230c919f7e3f3af3256161fbfaa0e2&hbe_qx_ui=1.3")
        result = self.run_script("easybike-ad.js", {"request": {"url": url, "method": "GET", "headers": {}}})
        response = result["done"]["response"]
        self.assertEqual(response["status"], 200)
        self.assertEqual(json.loads(response["body"])["type"], "container")

    def test_hellobike_request_stage_passes_through(self):
        result = self.run_script("easybike-ad.js", {
            "request": {"url": HELLOBIKE_API, "method": "POST", "headers": {}, "body": "x"},
        })
        self.assertEqual(result["done"], {})

    def popup_case(self, request_extra=None):
        popups = [
            {"popupWindowType": "marketAd", "popupWindowData": {"img": "ad"}},
            {"popupWindowType": "systemNotice", "popupWindowData": {"text": "keep"}},
        ]
        request = {"url": HELLOBIKE_API, "method": "POST", "headers": {"Content-Type": "text/plain"},
                   "plainBody": json.dumps({"action": "homepage.startup.popupWindow"})}
        request.update(request_extra or {})
        return {
            "aesKey": HELLOBIKE_STATIC_KEY,
            "request": request,
            "response": {"status": 200, "headers": {}, "plainBody": json.dumps({"code": 0, "data": popups})},
        }

    def test_hellobike_strips_ad_popup_without_qx_session_index(self):
        result = self.run_script("easybike-ad.js", self.popup_case())
        data = json.loads(result["plainBody"])["data"]
        self.assertEqual([p["popupWindowType"] for p in data], ["systemNotice"])

    def test_hellobike_accepts_binary_request_body(self):
        result = self.run_script("easybike-ad.js", self.popup_case({"asBytes": True}))
        data = json.loads(result["plainBody"])["data"]
        self.assertEqual([p["popupWindowType"] for p in data], ["systemNotice"])

    def test_hellobike_captures_dynamic_key_into_loon_store(self):
        payload = {"code": 0, "data": {
            "key": "abcdefghijklmnop", "key-version": "v9", "fingerprint-hash": "fp-1",
            "expired": int(time.time()) + 3600,
        }}
        result = self.run_script("easybike-ad.js", {
            "aesKey": HELLOBIKE_STATIC_KEY,
            "request": {"url": "https://api.hellobike.com/secretkey", "method": "POST", "headers": {}},
            "response": {"status": 200, "headers": {}, "plainBody": json.dumps(payload)},
        })
        cache = json.loads(result["store"]["HelloBikeQXKeyCacheV1"])
        self.assertEqual(cache["records"][0]["secret"], "abcdefghijklmnop")
        self.assertEqual(len(result["notifications"]), 1)
        self.assertIn("Loon", result["notifications"][0][2])
        self.assertNotIn("QX", result["notifications"][0][2])

    def test_hellobike_uses_captured_key(self):
        secret = "ponmlkjihgfedcba"
        store = {"HelloBikeQXKeyCacheV1": json.dumps({"version": 1, "records": [{
            "environment": "release", "secret": secret, "keyVersion": "v9",
            "fingerprint": "fp-1", "expires": int(time.time()) + 3600,
        }]})}
        case = self.popup_case({"headers": {"key-version": "v9", "fingerprint-hash": "fp-1"}})
        case["aesKey"] = secret
        case["store"] = store
        result = self.run_script("easybike-ad.js", case)
        data = json.loads(result["plainBody"])["data"]
        self.assertEqual([p["popupWindowType"] for p in data], ["systemNotice"])


if __name__ == "__main__":
    unittest.main()
