import { createWriteStream } from "node:fs";
import archiver from "archiver";

const output = createWriteStream("review-agent-edge-0.1.0.zip");
const archive = archiver("zip", { zlib: { level: 9 } });
archive.on("warning", (error) => {
  if (error.code !== "ENOENT") throw error;
});
archive.on("error", (error) => {
  throw error;
});
archive.pipe(output);
archive.directory("dist", false);
await archive.finalize();
