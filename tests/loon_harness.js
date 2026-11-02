// Runs one generated Loon script inside a mock of Loon's script API.
// Usage: node loon_harness.js <script.js>   (case JSON on stdin, result JSON on stdout)
//
// Case: {request, response?, store?, aesKey?, noTextCodec?}
//   request/response may carry `plainBody` instead of `body`: it is AES-128-CBC
//   encrypted with aesKey (key = iv, PKCS7, base64) the way HelloBike's API does,
//   `asBytes: true` to deliver the body as a Uint8Array (Loon binary-body-mode),
//   or `bodyBase64` to deliver raw bytes as a Uint8Array.
//   noTextCodec hides TextDecoder/TextEncoder, which Loon's JS engine may lack.
// Result: {done, doneCalls, store, notifications, removeCalled, plainBody?}
//   A Uint8Array done.body is reported as {bodyBase64} instead.
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
  if (out.bodyBase64 !== undefined) {
    out.body = new Uint8Array(Buffer.from(out.bodyBase64, "base64"));
    delete out.bodyBase64;
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
};
if (!testCase.noTextCodec) Object.assign(sandbox, { TextDecoder, TextEncoder });
if (testCase.response) sandbox.$response = prepare(testCase.response);

vm.runInNewContext(fs.readFileSync(scriptPath, "utf8"), sandbox, { filename: scriptPath, timeout: 10000 });

let done = doneCalls[0];
if (done && typeof done === "object" && done.body != null && typeof done.body === "object") {
  if (!ArrayBuffer.isView(done.body)) throw new Error("done.body is neither string nor Uint8Array");
  done = Object.assign({}, done, { body: undefined, bodyBase64: Buffer.from(done.body).toString("base64") });
  delete done.body;
}
const result = { done, doneCalls: doneCalls.length, store, notifications, removeCalled };
if (testCase.aesKey && done && typeof done.body === "string" && done.body) {
  result.plainBody = decrypt(done.body, testCase.aesKey);
}
process.stdout.write(JSON.stringify(result));
