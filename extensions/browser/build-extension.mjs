import { copyFile } from "node:fs/promises";
import * as esbuild from "esbuild";

await esbuild.build({
  entryPoints: ["src/background.ts"],
  bundle: true,
  outfile: "dist/background.js",
  format: "esm",
  platform: "browser",
  target: "chrome114",
  minify: true,
});

await copyFile("manifest.json", "dist/manifest.json");
