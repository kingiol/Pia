import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourceRoot = path.join(projectRoot, "node_modules/@phosphor-icons/core/assets/regular");
const outputRoot = path.join(projectRoot, "apps/android/app/src/main/res/drawable");
const icons = ["sun", "chart-line", "bell", "arrow-clockwise", "sparkle", "plus-circle"];

await mkdir(outputRoot, { recursive: true });

for (const name of icons) {
  const source = await readFile(path.join(sourceRoot, `${name}.svg`), "utf8");
  const pathData = source.match(/<path d="([^"]+)"/)?.[1];
  if (!pathData) throw new Error(`Missing path data for ${name}`);

  const resourceName = `ic_phosphor_${name.replaceAll("-", "_")}`;
  const vector = `<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="24dp" android:height="24dp" android:viewportWidth="256" android:viewportHeight="256">
    <path android:fillColor="#FF000000" android:pathData="${pathData}" />
</vector>
`;
  await writeFile(path.join(outputRoot, `${resourceName}.xml`), vector);
}
