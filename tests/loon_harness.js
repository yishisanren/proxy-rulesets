// Runs one generated Loon script inside a mock of Loon's script API.
// Usage: node loon_harness.js <script.js>   (case JSON on stdin, result JSON on stdout)
//
// Case: {request, response?, store?, aesKey?}
//   request/response may carry `plainBody` instead of `body`: it is AES-128-CBC
//   encrypted with aesKey (key = iv, PKCS7, base64) the way HelloBike's API does,
//   and `asBytes: true` to deliver the body as a Uint8Array.
// Result: {done, doneCalls, store, notifications, removeCalled, plainBody?}
"use strict";
const fs = require("fs");
const vm = require("vm");
const crypto = require("crypto");

const scriptPath = process.argv[2];
const testCase = JSON.parse(fs.readFileSync(0, "utf8"));

function encrypt(text, key) {
  const k = Buffer.from(key, "utf8");
  const c = crypto.createCipheriv("aes-128-cbc", k, k);
  return Buffer.concat([c.update(text, "utf8"), c.final()]).toString("base64");
}
function decrypt(b64, key) {
  const k = Buffer.from(key, "utf8");
  const d = crypto.createDecipheriv("aes-128-cbc", k, k);
  return Buffer.concat([d.update(Buffer.from(b64, "base64")), d.final()]).toString("utf8");
}
function prepare(msg) {
  if (!msg) return undefined;
  const out = Object.assign({}, msg);
  if (out.plainBody !== undefined) {
    out.body = encrypt(out.plainBody, testCase.aesKey);
    delete out.plainBody;
  }
  if (out.asBytes) {
    out.body = new Uint8Array(Buffer.from(out.body, "utf8"));
    delete out.asBytes;
  }
  return out;
}

const store = Object.assign({}, testCase.store || {});
const notifications = [];
const doneCalls = [];
let removeCalled = false;

const sandbox = {
  $loon: "iPhone 17.0 3.3.0 (900)",
  $request: prepare(testCase.request),
  $persistentStore: {
    read: (key) => (Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null),
    write: (value, key) => { store[key] = value; return true; },
    remove: () => { removeCalled = true; for (const k of Object.keys(store)) delete store[k]; return true; },
  },
  $notification: { post: (title, subtitle, body) => notifications.push([title, subtitle, body]) },
  $done: (value) => doneCalls.push(value === undefined ? null : value),
  console,
  TextDecoder,
};
if (testCase.response) sandbox.$response = prepare(testCase.response);

vm.runInNewContext(fs.readFileSync(scriptPath, "utf8"), sandbox, { filename: scriptPath, timeout: 10000 });

const done = doneCalls[0];
const result = { done, doneCalls: doneCalls.length, store, notifications, removeCalled };
if (testCase.aesKey && done && typeof done.body === "string" && done.body) {
  result.plainBody = decrypt(done.body, testCase.aesKey);
}
process.stdout.write(JSON.stringify(result));
