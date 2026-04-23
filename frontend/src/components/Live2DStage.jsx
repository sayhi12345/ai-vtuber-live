import { useEffect, useRef, useState } from "react";
import StageAvatar from "./StageAvatar";

const DEFAULT_MODEL_PATH =
  import.meta.env.VITE_LIVE2D_MODEL_PATH || "/live2d/haru/haru_greeter_t03.model3.json";
const DEFAULT_CORE_SCRIPT_PATH =
  import.meta.env.VITE_LIVE2D_CORE_SCRIPT_PATH || "/live2d/live2dcubismcore.min.js";
const MOUTH_PARAM_ID = "ParamMouthOpenY";
const FALLBACK_LIP_SYNC_PARAMS = [MOUTH_PARAM_ID];
const HALF_BODY_WIDTH_RATIO = 0.9;
const HALF_BODY_HEIGHT_RATIO = 1.4;
const HALF_BODY_Y_RATIO = 0.66;
const ANGLE_MAX = 30;
const CLICK_THRESHOLD_PX = 10;
// Map TTS emotion names → Live2D expression names (Haru model F01–F08)
const EMOTION_TO_EXPRESSION = {
  happy: "F02",
  angry: "F03",
  sad: "F04",
  surprised: "F05",
};
let cubismCoreReadyPromise = null;

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function clamp01(value) {
  return clamp(value, 0, 1);
}

function getLipSyncParamIds(model) {
  const ids = model?.internalModel?.settings?.getLipSyncParameters?.();
  return Array.isArray(ids) && ids.length ? ids : FALLBACK_LIP_SYNC_PARAMS;
}

function getModelSize(model) {
  const bounds = model?.getLocalBounds?.();
  if (bounds?.width && bounds?.height) {
    return { width: bounds.width, height: bounds.height };
  }
  return { width: model?.width || 1, height: model?.height || 1 };
}

function ensureCubismCoreScript() {
  if (window.Live2DCubismCore) return Promise.resolve();
  if (cubismCoreReadyPromise) return cubismCoreReadyPromise;

  cubismCoreReadyPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-live2d-core="1"]');
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener(
        "error",
        () => reject(new Error("Failed to load live2dcubismcore script.")),
        { once: true }
      );
      return;
    }
    const script = document.createElement("script");
    script.src = DEFAULT_CORE_SCRIPT_PATH;
    script.async = true;
    script.dataset.live2dCore = "1";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load live2dcubismcore script."));
    document.head.appendChild(script);
  });

  return cubismCoreReadyPromise;
}

export default function Live2DStage({
  expression,
  mouthOpen,
  subtitle,
  speaking,
  transparent = false,
  modelPath = DEFAULT_MODEL_PATH,
  onLoadError
}) {
  const hostRef = useRef(null);
  const appRef = useRef(null);
  const modelRef = useRef(null);
  const mouthTargetRef = useRef(0);
  const mouthCurrentRef = useRef(0);
  const speakingRef = useRef(false);
  const lipSyncParamIdsRef = useRef(FALLBACK_LIP_SYNC_PARAMS);
  const onLoadErrorRef = useRef(onLoadError);
  const expressionRef = useRef(expression);
  // { dragging, targetX, targetY } — updated by pointer events, consumed in beforeModelUpdate
  const angleDragRef = useRef({ dragging: false, targetX: 0, targetY: 0 });
  // smoothed current angles applied to the model each frame
  const angleCurrentRef = useRef({ x: 0, y: 0 });
  // pointer position at pointerdown — used to distinguish click from drag
  const pointerDownPosRef = useRef(null);
  const [loadError, setLoadError] = useState("");

  mouthTargetRef.current = clamp01(mouthOpen);
  speakingRef.current = speaking;

  useEffect(() => {
    onLoadErrorRef.current = onLoadError;
  }, [onLoadError]);

  // Apply emotion→expression whenever the prop changes
  useEffect(() => {
    expressionRef.current = expression;
    const model = modelRef.current;
    if (!model) return;
    const exprId = EMOTION_TO_EXPRESSION[expression];
    // null resets to the model's default (no expression)
    model.expression(exprId ?? null);
  }, [expression]);

  useEffect(() => {
    let canceled = false;
    let resizeHandler = null;
    let beforeModelUpdateHandler = null;
    let canvasPointerDown = null;
    let windowPointerMove = null;
    let windowPointerUp = null;

    const setup = async () => {
      if (!hostRef.current) return;
      try {
        await ensureCubismCoreScript();
        const PIXI = await import("pixi.js");
        window.PIXI = PIXI;
        const { Live2DModel } = await import("pixi-live2d-display/cubism4");
        if (canceled || !hostRef.current) return;

        const app = new PIXI.Application({
          resizeTo: hostRef.current,
          autoDensity: true,
          antialias: true,
          backgroundAlpha: 0
        });
        hostRef.current.innerHTML = "";
        hostRef.current.appendChild(app.view);

        const model = await Live2DModel.from(modelPath, { autoInteract: false });
        if (canceled) {
          app.destroy(true);
          return;
        }

        model.anchor.set(0.5, 0.5);
        app.stage.addChild(model);
        appRef.current = app;
        modelRef.current = model;
        mouthCurrentRef.current = 0;
        lipSyncParamIdsRef.current = getLipSyncParamIds(model);

        // Start idle loop
        model.motion("Idle");

        // Apply any expression that arrived before the model was ready
        const initExpr = EMOTION_TO_EXPRESSION[expressionRef.current];
        if (initExpr) model.expression(initExpr);

        const layoutModel = () => {
          if (!hostRef.current || !modelRef.current) return;
          const { clientWidth, clientHeight } = hostRef.current;
          if (!clientWidth || !clientHeight) return;
          const { width: modelWidth, height: modelHeight } = getModelSize(modelRef.current);
          const scale = Math.min(
            (clientWidth * HALF_BODY_WIDTH_RATIO) / modelWidth,
            (clientHeight * HALF_BODY_HEIGHT_RATIO) / modelHeight
          );
          modelRef.current.scale.set(scale);
          modelRef.current.position.set(clientWidth * 0.5, clientHeight * HALF_BODY_Y_RATIO);
        };
        layoutModel();
        resizeHandler = () => layoutModel();
        window.addEventListener("resize", resizeHandler);

        // ── Pointer interaction ──────────────────────────────────────────────

        const canvas = app.view;

        canvasPointerDown = (e) => {
          pointerDownPosRef.current = { x: e.clientX, y: e.clientY };
          angleDragRef.current.dragging = true;
        };

        windowPointerMove = (e) => {
          if (!angleDragRef.current.dragging) return;
          const rect = canvas.getBoundingClientRect();
          const cx = rect.left + rect.width * 0.5;
          const cy = rect.top + rect.height * HALF_BODY_Y_RATIO;
          angleDragRef.current.targetX = clamp(
            ((e.clientX - cx) / (rect.width * 0.5)) * ANGLE_MAX,
            -ANGLE_MAX,
            ANGLE_MAX
          );
          angleDragRef.current.targetY = clamp(
            (-(e.clientY - cy) / (rect.height * 0.5)) * ANGLE_MAX,
            -ANGLE_MAX,
            ANGLE_MAX
          );
        };

        windowPointerUp = (e) => {
          if (!angleDragRef.current.dragging) return;
          angleDragRef.current.dragging = false;
          angleDragRef.current.targetX = 0;
          angleDragRef.current.targetY = 0;

          // Fire hit-test only when the pointer barely moved (i.e. a tap/click)
          const pd = pointerDownPosRef.current;
          if (pd && Math.hypot(e.clientX - pd.x, e.clientY - pd.y) < CLICK_THRESHOLD_PX) {
            const rect = canvas.getBoundingClientRect();
            const scaleX = canvas.width / rect.width;
            const scaleY = canvas.height / rect.height;
            const canvasX = (e.clientX - rect.left) * scaleX;
            const canvasY = (e.clientY - rect.top) * scaleY;
            const hits = modelRef.current?.hitTest(canvasX, canvasY) || [];
            if (hits.includes("Head")) {
              modelRef.current?.motion("Tap");
            } else if (hits.includes("Body")) {
              modelRef.current?.expression("F04"); // shy/blush
              modelRef.current?.motion("Tap");
            }
          }
          pointerDownPosRef.current = null;
        };

        canvas.addEventListener("pointerdown", canvasPointerDown);
        window.addEventListener("pointermove", windowPointerMove);
        window.addEventListener("pointerup", windowPointerUp);

        // ── Per-frame parameter overrides ───────────────────────────────────

        beforeModelUpdateHandler = () => {
          const coreModel = modelRef.current?.internalModel?.coreModel;
          if (!coreModel?.setParameterValueById) return;

          // Lip-sync
          let targetValue = mouthTargetRef.current;
          if (speakingRef.current && targetValue > 0) {
            targetValue = Math.max(targetValue, 0.04);
          }
          const currentValue = mouthCurrentRef.current;
          const smoothing = targetValue > currentValue ? 0.48 : 0.22;
          const nextValue = currentValue + (targetValue - currentValue) * smoothing;
          mouthCurrentRef.current = nextValue < 0.01 ? 0 : nextValue;
          for (const paramId of lipSyncParamIdsRef.current) {
            coreModel.setParameterValueById(paramId, mouthCurrentRef.current, 1);
          }

          // Head angle (drag-to-look + smooth return)
          const drag = angleDragRef.current;
          const angle = angleCurrentRef.current;
          angle.x += (drag.targetX - angle.x) * 0.12;
          angle.y += (drag.targetY - angle.y) * 0.12;
          if (drag.dragging || Math.abs(angle.x) > 0.05 || Math.abs(angle.y) > 0.05) {
            coreModel.setParameterValueById("ParamAngleX", angle.x, 1);
            coreModel.setParameterValueById("ParamAngleY", angle.y, 1);
          }
        };
        model.internalModel.on("beforeModelUpdate", beforeModelUpdateHandler);
        setLoadError("");
      } catch (error) {
        const reason = error instanceof Error ? error.message : "Unknown error";
        setLoadError(reason);
        onLoadErrorRef.current?.(reason);
      }
    };

    setup();

    return () => {
      canceled = true;
      if (modelRef.current?.internalModel && beforeModelUpdateHandler) {
        modelRef.current.internalModel.off("beforeModelUpdate", beforeModelUpdateHandler);
      }
      if (resizeHandler) window.removeEventListener("resize", resizeHandler);
      if (appRef.current?.view && canvasPointerDown) {
        appRef.current.view.removeEventListener("pointerdown", canvasPointerDown);
      }
      if (windowPointerMove) window.removeEventListener("pointermove", windowPointerMove);
      if (windowPointerUp) window.removeEventListener("pointerup", windowPointerUp);
      if (modelRef.current) {
        modelRef.current.destroy();
        modelRef.current = null;
      }
      if (appRef.current) {
        appRef.current.destroy(true);
        appRef.current = null;
      }
    };
  }, [modelPath]);

  if (loadError) {
    return (
      <StageAvatar
        expression={expression}
        mouthOpen={mouthOpen}
        subtitle={subtitle}
        speaking={speaking}
        transparent={transparent}
      />
    );
  }

  return (
    <section className={`stage-shell ${transparent ? "transparent" : ""}`}>
      <div ref={hostRef} className="live2d-host" />
      <div className="subtitle-box">{subtitle || "..."}</div>
    </section>
  );
}
