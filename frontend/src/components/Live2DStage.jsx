import { useEffect, useRef, useState } from "react";
import StageAvatar from "./StageAvatar";

const DEFAULT_MODEL_PATH =
  import.meta.env.VITE_LIVE2D_MODEL_PATH || "/live2d/haru/haru_greeter_t03.model3.json";
const DEFAULT_CORE_SCRIPT_PATH =
  import.meta.env.VITE_LIVE2D_CORE_SCRIPT_PATH || "/live2d/live2dcubismcore.min.js";
const MOUTH_PARAM_ID = "ParamMouthOpenY";
const FALLBACK_LIP_SYNC_PARAMS = [MOUTH_PARAM_ID];
let cubismCoreReadyPromise = null;

function clamp01(value) {
  return Math.max(0, Math.min(1, value));
}

function getLipSyncParamIds(model) {
  const ids = model?.internalModel?.settings?.getLipSyncParameters?.();
  return Array.isArray(ids) && ids.length ? ids : FALLBACK_LIP_SYNC_PARAMS;
}

function ensureCubismCoreScript() {
  if (window.Live2DCubismCore) {
    return Promise.resolve();
  }
  if (cubismCoreReadyPromise) {
    return cubismCoreReadyPromise;
  }

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
  const [loadError, setLoadError] = useState("");

  mouthTargetRef.current = clamp01(mouthOpen);
  speakingRef.current = speaking;

  useEffect(() => {
    onLoadErrorRef.current = onLoadError;
  }, [onLoadError]);

  useEffect(() => {
    let canceled = false;
    let resizeHandler = null;
    let beforeModelUpdateHandler = null;

    const setup = async () => {
      if (!hostRef.current) {
        return;
      }
      try {
        await ensureCubismCoreScript();
        const PIXI = await import("pixi.js");
        window.PIXI = PIXI;
        const { Live2DModel } = await import("pixi-live2d-display/cubism4");
        // this could be "pixi-live2d-display/lib/cubism4" in older version
        if (canceled || !hostRef.current) {
          return;
        }

        const app = new PIXI.Application({
          resizeTo: hostRef.current,
          autoDensity: true,
          antialias: true,
          backgroundAlpha: 0
        });
        hostRef.current.innerHTML = "";
        hostRef.current.appendChild(app.view);

        const model = await Live2DModel.from(modelPath, {
          autoInteract: false
        });
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

        const layoutModel = () => {
          if (!hostRef.current || !modelRef.current) {
            return;
          }
          const { clientWidth, clientHeight } = hostRef.current;
          if (!clientWidth || !clientHeight) {
            return;
          }
          const scale = Math.min(
            (clientWidth * 0.82) / modelRef.current.width,
            (clientHeight * 0.88) / modelRef.current.height
          );
          modelRef.current.scale.set(scale);
          modelRef.current.position.set(clientWidth * 0.5, clientHeight * 0.52);
        };
        layoutModel();
        resizeHandler = () => layoutModel();
        window.addEventListener("resize", resizeHandler);

        beforeModelUpdateHandler = () => {
          const target = modelRef.current;
          const coreModel = target?.internalModel?.coreModel;
          if (!coreModel?.setParameterValueById) {
            return;
          }

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
      if (resizeHandler) {
        window.removeEventListener("resize", resizeHandler);
      }
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

  // TODO: map emotion state to model expressions/motions in a follow-up iteration.
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
