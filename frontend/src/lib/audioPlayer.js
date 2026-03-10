function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function createAudioPlayer({ onAmplitude, onStart, onEnd }) {
  let context = null;
  let audio = null;
  let source = null;
  let analyser = null;
  let rafId = null;
  let objectUrl = null;
  let smoothedAmplitude = 0;

  const cleanupGraph = () => {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    if (source) {
      source.disconnect();
      source = null;
    }
    if (analyser) {
      analyser.disconnect();
      analyser = null;
    }
    if (audio) {
      audio.pause();
      audio.src = "";
      audio = null;
    }
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
    smoothedAmplitude = 0;
    onAmplitude?.(0);
    onEnd?.();
  };

  const stop = () => {
    cleanupGraph();
  };

  const playBlob = async (blob) => {
    stop();
    if (!blob) {
      return;
    }

    onStart?.();
    objectUrl = URL.createObjectURL(blob);
    audio = new Audio(objectUrl);
    audio.preload = "auto";

    if (!context) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      context = Ctx ? new Ctx() : null;
    }

    if (!context) {
      await audio.play();
      await sleep(Math.max(300, audio.duration * 1000 || 600));
      cleanupGraph();
      return;
    }

    if (context.state === "suspended") {
      await context.resume();
    }

    source = context.createMediaElementSource(audio);
    analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    analyser.connect(context.destination);

    const data = new Uint8Array(analyser.fftSize);
    const amplitudeTick = () => {
      if (!analyser) {
        return;
      }
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i += 1) {
        const normalized = (data[i] - 128) / 128;
        sum += normalized * normalized;
      }
      const rms = Math.sqrt(sum / data.length);
      const boostedAmplitude = Math.min(1, rms * 12);
      const gatedAmplitude = boostedAmplitude < 0.025 ? 0 : boostedAmplitude;
      const smoothing =
        gatedAmplitude > smoothedAmplitude ? 0.46 : gatedAmplitude === 0 ? 0.2 : 0.24;
      smoothedAmplitude += (gatedAmplitude - smoothedAmplitude) * smoothing;
      onAmplitude?.(smoothedAmplitude < 0.01 ? 0 : smoothedAmplitude);
      rafId = requestAnimationFrame(amplitudeTick);
    };
    amplitudeTick();

    await audio.play();
    await new Promise((resolve, reject) => {
      audio.addEventListener("ended", resolve, { once: true });
      audio.addEventListener("error", reject, { once: true });
    });
    cleanupGraph();
  };

  return { playBlob, stop };
}
