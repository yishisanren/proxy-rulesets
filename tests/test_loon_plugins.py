import base64
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
TXSPORTS_UA = {"User-Agent": "QQSportsV3/8.2.5 (iPhone; iOS 18.1)"}
TXSPORTS_AB = "https://config.ab.qq.com/tab/GetTabRemoteConfig?appid=sports"


def pb_varint(n):
    out = bytearray()
    while n >= 0x80:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def pb_bytes(field, payload):
    return pb_varint(field << 3 | 2) + pb_varint(len(payload)) + payload


def pb_parse(buf):
    """Decode one protobuf message into [(field, wire, value)]."""
    fields, p = [], 0
    while p < len(buf):
        tag, shift = 0, 0
        while True:
            b = buf[p]; p += 1
            tag |= (b & 0x7F) << shift; shift += 7
            if not b & 0x80:
                break
        field, wire = tag >> 3, tag & 7
        if wire == 0:
            v, shift = 0, 0
            while True:
                b = buf[p]; p += 1
                v |= (b & 0x7F) << shift; shift += 7
                if not b & 0x80:
                    break
        elif wire == 2:
            n, shift = 0, 0
            while True:
                b = buf[p]; p += 1
                n |= (b & 0x7F) << shift; shift += 7
                if not b & 0x80:
                    break
            v = buf[p:p + n]; p += n
        else:
            raise ValueError(wire)
        fields.append((field, wire, v))
    return fields


def ab_config(entries, code=100):
    """Tencent AB config response: field 1 = code, field 3 = {1: key, 2: {1: value, 4: key}}."""
    msg = pb_varint(1 << 3) + pb_varint(code)
    for key, value in entries:
        k = key.encode()
        msg += pb_bytes(3, pb_bytes(1, k) + pb_bytes(2, pb_bytes(1, value.encode()) + pb_bytes(4, k)))
    return msg


def ab_values(msg):
    out = {}
    for field, _, entry in pb_parse(msg):
        if field != 3:
            continue
        parts = dict((f, v) for f, _, v in pb_parse(entry))
        inner = dict((f, v) for f, _, v in pb_parse(parts[2]))
        out[parts[1].decode()] = inner[1].decode()
    return out


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

    def test_binary_scripts_get_binary_body_mode(self):
        snippet = qx2loon.parse_snippet(
            "^https://a\\.com/z url script-response-body https://e.com/s.js\n"
            "^https://a\\.com/h url script-response-header https://e.com/s.js\n"
        )
        plugin = qx2loon.render_plugin({"id": "demo", "snippet": "x"}, snippet, {"s.js"})
        self.assertIn("requires-body=true, binary-body-mode=true, tag=demo-s-1", plugin)
        self.assertIn("s.js, tag=demo-s-2", plugin)
        self.assertNotIn("binary-body-mode", qx2loon.render_plugin({"id": "demo", "snippet": "x"}, snippet))

    def test_url_and_header_needs_script_side_check(self):
        line = ("^https:\\/\\/a\\.com\\/t(?:\\?.*)?$ (?i)\\r\\nUser-Agent:\\s*App\\/ "
                "url-and-header script-response-body https://e.com/s.js")
        snippet = qx2loon.parse_snippet(line)
        self.assertEqual(snippet["scripts"][0]["pattern"], "^https:\\/\\/a\\.com\\/t(?:\\?.*)?$")
        with self.assertRaises(qx2loon.ConvertError):
            qx2loon.render_plugin({"id": "demo", "snippet": "x"}, snippet)
        plugin = qx2loon.render_plugin({"id": "demo", "snippet": "x", "header_match_in_script": ["s.js"]}, snippet)
        self.assertIn("http-response ^https:\\/\\/a\\.com\\/t(?:\\?.*)?$ script-path=", plugin)
        self.assertNotIn("User-Agent", plugin)
        for bad in (
            "^https://a\\.com/t url-and-header script-response-body https://e.com/s.js",
            "^https://a\\.com/t\\r\\nUA:x url-and-header reject",
        ):
            with self.assertRaises(qx2loon.ConvertError, msg=bad):
                qx2loon.parse_snippet(bad)


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


    # --- Tencent Sports (txsports-ad-clean.js runs with binary-body-mode) ---

    def tx_json(self, url, body, headers=None, request_body=None, **case):
        request = {"url": url, "method": "GET", "headers": headers or TXSPORTS_UA}
        if request_body is not None:
            request.update(method="POST", body=request_body, asBytes=True)
        raw = json.dumps(body, ensure_ascii=False)
        case.setdefault("noTextCodec", True)
        result = self.run_script("txsports-ad-clean.js", dict(case, request=request, response={
            "status": 200, "headers": {}, "body": raw, "asBytes": True,
        }))
        done = result["done"]
        if "bodyBase64" in done:
            return json.loads(base64.b64decode(done["bodyBase64"]).decode("utf-8"))
        self.assertNotIn("body", done, "binary-body-mode needs a Uint8Array body back")
        return None

    def test_txsports_forces_splash_off_in_binary_ab_config(self):
        original = ab_config([("iqad_splash_forbid_splash", "0"), ("other_switch", "keep")])
        for codec in (True, False):
            result = self.run_script("txsports-ad-clean.js", {
                "noTextCodec": not codec,
                "request": {"url": TXSPORTS_AB, "method": "POST", "headers": TXSPORTS_UA},
                "response": {"status": 200, "headers": {}, "bodyBase64": base64.b64encode(original).decode()},
            })
            patched = base64.b64decode(result["done"]["bodyBase64"])
            self.assertEqual(ab_values(patched), {
                "iqad_splash_forbid_splash": "1",
                "other_switch": "keep",
                "teenager_guide_show_interval": "36500",
            })
            self.assertEqual(pb_parse(patched)[0], (1, 0, 100))

    def test_txsports_leaves_other_tencent_apps_alone(self):
        original = ab_config([("iqad_splash_forbid_splash", "0")])
        result = self.run_script("txsports-ad-clean.js", {
            "request": {"url": TXSPORTS_AB, "method": "POST", "headers": {"User-Agent": "QQ/9.0.85 iOS"}},
            "response": {"status": 200, "headers": {}, "bodyBase64": base64.b64encode(original).decode()},
        })
        self.assertEqual(result["done"], {})

    def test_txsports_hides_middle_icon(self):
        body = self.tx_json("https://app.sports.qq.com/init/config?v=1",
                            {"code": 0, "data": {"middleIcon": {"isAble": "1", "title": "会员"}}})
        self.assertEqual(body["data"]["middleIcon"], {"isAble": "0", "title": "会员"})

    def test_txsports_cleans_home_feed(self):
        feed = {"data": {
            "hotWords": ["热词"], "coinIcon": {"x": 1}, "adList": "{}",
            "topItem": [{"type": 1120}, {"type": 1, "adInfos": [{"id": 1}]}],
            "list": [{"title": "中超直播", "adInfos": [{"id": 2}]}],
        }}
        for codec in (True, False):
            d = self.tx_json("https://app.sports.qq.com/feeds/home", feed, noTextCodec=not codec)["data"]
            self.assertEqual(d["hotWords"], [])
            self.assertNotIn("coinIcon", d)
            self.assertEqual(d["adList"], "")
            self.assertEqual(d["topItem"], [{"type": 1, "adInfos": []}])
            self.assertEqual(d["list"], [{"title": "中超直播", "adInfos": []}])

    def test_txsports_unchanged_json_passes_through(self):
        self.assertIsNone(self.tx_json("https://app.sports.qq.com/init/config", {"data": {"middleIcon": {"isAble": "0"}}}))

    def test_txsports_drops_ssp_ad_order_using_request_body(self):
        req = json.dumps({"adReqData": {"adtype": 7, "chid": 5, "launch": "0", "slot": [{"loid": "71,73"}]}})
        resp = {"adList": json.dumps({"index": [{"channel_id": 7247}], "order": [{"oid": 1}]})}
        body = self.tx_json("https://sports.ssp.qq.com/app", resp, request_body=req)
        self.assertEqual(json.loads(body["adList"])["order"], [])

    def test_txsports_turns_off_sdk_ads_in_xml(self):
        xml = "<dict><key>adOn</key><string>YES</string><key>gdtAdOn</key> <string>YES</string></dict>"
        result = self.run_script("txsports-ad-clean.js", {
            "noTextCodec": True,
            "request": {"url": "https://k.ssp.qq.com/getsdkconfig?x=1", "method": "GET", "headers": TXSPORTS_UA},
            "response": {"status": 200, "headers": {}, "body": xml, "asBytes": True},
        })
        out = base64.b64decode(result["done"]["bodyBase64"]).decode()
        self.assertEqual(out.count("<string>NO</string>"), 2)


if __name__ == "__main__":
    unittest.main()
