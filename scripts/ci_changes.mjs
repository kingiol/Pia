import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";

export const surfaces = ["runtime", "contracts", "web", "desktop", "platform", "android", "ios", "docs"];

export function classifyChanges(paths) {
  const result = Object.fromEntries(surfaces.map((name) => [name, false]));
  const enable = (...names) => names.forEach((name) => { result[name] = true; });
  for (const path of paths) {
    if (/^(docs\/.*\.(md|png|jpe?g|webp|svg)|[^/]+\.md)$/.test(path)) enable("docs");
    else if (/^(contracts\/|packages\/contracts\/|scripts\/generate_)/.test(path)) enable("contracts", "runtime", "web", "desktop");
    else if (/^(apps\/desktop\/src\/|apps\/web\/)/.test(path)) enable("web", "desktop");
    else if (/^(apps\/desktop\/src-tauri\/|sidecar|scripts\/(build-sidecar|desktop-|windows-))/.test(path)) enable("runtime", "web", "desktop", "platform");
    else if (/^apps\/android\//.test(path)) enable("android");
    else if (/^apps\/ios\//.test(path)) enable("ios");
    else if (/^(pyproject\.toml$|packages-py\/pia_runtime\/pia_runtime\/(cli|config|isolated_call)\.py$)/.test(path)) enable("runtime", "platform");
    else if (/^(packages-py\/|pyproject\.toml$|migrations\/|rules\/|config\/)/.test(path)) enable("runtime");
    else if (/^tests\//.test(path)) enable("runtime", "contracts");
    else if (/^(package\.json|pnpm-lock\.yaml)$/.test(path)) enable("contracts", "web", "desktop");
    else enable(...surfaces);
  }
  if (!paths.length) enable("docs");
  return result;
}

export function requiredGate(changes, jobs) {
  return jobs.changes === "success" && surfaces.every((name) =>
    changes[name] === true ? jobs[name] === "success" : ["success", "skipped"].includes(jobs[name]));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (process.argv[2] === "--gate") {
    const needs = JSON.parse(process.env.CI_NEEDS || "{}");
    const changes = Object.fromEntries(surfaces.map((name) => [name, needs.changes?.outputs?.[name] === "true"]));
    if (!surfaces.every((name) => ["true", "false"].includes(needs.changes?.outputs?.[name])) ||
        !requiredGate(changes, Object.fromEntries(Object.entries(needs).map(([name, job]) => [name, job.result])))) {
      console.error("A required job failed, was cancelled, or was unexpectedly skipped.");
      process.exitCode = 1;
    }
  } else {
    const [base, head] = process.argv.slice(2);
    if (!base || !head) throw new Error("Expected explicit base and head revisions");
    const paths = execFileSync("git", ["diff", "--no-renames", "--name-only", "-z", base, head], { encoding: "utf8" }).split("\0").filter(Boolean);
    for (const [name, value] of Object.entries(classifyChanges(paths))) console.log(`${name}=${value}`);
  }
}
