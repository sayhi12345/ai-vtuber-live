import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const motionPath = resolve(
  root,
  "public/live2d/haru/motion/haru_g_arms_crossed.motion3.json"
);

assert.ok(existsSync(motionPath), "arms-crossed motion file exists");

const motion = JSON.parse(readFileSync(motionPath, "utf8"));
const model = JSON.parse(
  readFileSync(resolve(root, "public/live2d/haru/haru_greeter_t03.model3.json"), "utf8")
);
const stage = readFileSync(resolve(root, "src/components/Live2DStage.jsx"), "utf8");
const curveIds = new Set(motion.Curves.map(({ Id }) => Id));

assert.equal(motion.Version, 3);
assert.equal(motion.Meta.Loop, false);
for (const id of [
  "ParamArmLA",
  "ParamArmLB",
  "ParamArmRA",
  "ParamArmRB",
  "ParamHandAngleL",
  "ParamHandAngleR"
]) {
  assert.ok(curveIds.has(id), `motion controls ${id}`);
}
assert.equal(
  model.FileReferences.Motions.ArmsCrossed[0].File,
  "motion/haru_g_arms_crossed.motion3.json"
);
assert.match(
  stage,
  /hits\.includes\("Body"\)[\s\S]*?motion\("ArmsCrossed"\)/,
  "body click starts ArmsCrossed"
);
assert.match(
  stage,
  /model\.motion\("Idle", 0, MotionPriority\.IDLE\)/,
  "idle priority leaves normal motions unblocked"
);
