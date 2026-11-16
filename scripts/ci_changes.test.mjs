import test from "node:test";
import assert from "node:assert/strict";
import { classifyChanges, requiredGate, surfaces } from "./ci_changes.mjs";

test("paths select every shared consumer and keep docs offline", () => {
  for (const path of ["README.md", "docs/INDEX.md", "docs/image.png"]) {
    assert.deepEqual(Object.entries(classifyChanges([path])).filter(([, value]) => value).map(([key]) => key), ["docs"]);
  }
  const examples = [
    ["packages-py/pia_runtime/runtime.py", ["runtime"]],
    ["contracts/schemas/task.json", ["runtime", "contracts", "web", "desktop"]],
    ["apps/desktop/src/App.tsx", ["web", "desktop"]],
    ["apps/desktop/src-tauri/src/main.rs", ["platform"]],
    ["apps/android/app/build.gradle.kts", ["android"]],
    ["apps/ios/PiaMobileClient/Package.swift", ["ios"]],
    ["packages-py/pia_runtime/pia_runtime/isolated_call.py", ["runtime", "platform"]],
    ["pyproject.toml", ["runtime", "platform"]],
    ["pnpm-lock.yaml", ["contracts", "web", "desktop"]],
  ];
  for (const [path, expected] of examples) {
    const selected = classifyChanges([path]);
    expected.forEach((name) => assert.equal(selected[name], true, `${path}: ${name}`));
  }
});

test("unknown paths and workflows conservatively run everything", () => {
  for (const path of [".github/workflows/ci.yml", "scripts/test.sh", "unknown.xyz", ".newconfig"]) {
    assert.ok(Object.values(classifyChanges([path])).every(Boolean));
  }
  const rename = classifyChanges(["apps/desktop/src/Old.tsx", "apps/android/New.kt"]);
  assert.ok(rename.desktop && rename.web && rename.android);
});

test("aggregate rejects every unexpected job outcome", () => {
  const changes = classifyChanges(["README.md"]);
  const jobs = Object.fromEntries(surfaces.map((name) => [name, changes[name] ? "success" : "skipped"]));
  jobs.changes = "success";
  assert.equal(requiredGate(changes, jobs), true);
  for (const status of ["failure", "cancelled", "skipped"]) {
    assert.equal(requiredGate(changes, { ...jobs, docs: status }), false);
  }
  assert.equal(requiredGate(changes, { ...jobs, changes: "failure" }), false);
});
