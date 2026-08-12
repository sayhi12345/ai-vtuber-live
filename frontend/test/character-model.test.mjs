import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const app = readFileSync(resolve(root, "src/App.jsx"), "utf8");

assert.match(
  app,
  /<Live2DStage[\s\S]*?modelPath=\{currentCharacter\?\.avatar \|\| undefined\}/,
  "chat stage uses the selected character avatar"
);
assert.match(
  app,
  /function StagePage\(\)[\s\S]*?character_id[\s\S]*?<Live2DStage[\s\S]*?modelPath=\{currentCharacter\?\.avatar \|\| undefined\}/,
  "standalone stage resolves the session character avatar"
);
assert.match(
  app,
  /url\.searchParams\.set\("character_id", session\.character_id\)/,
  "stage URL uses the character bound to the minted session"
);
