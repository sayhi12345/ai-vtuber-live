Live2D assets are stored here.

Current default model:

- `haru/haru_greeter_t03.model3.json`

Example folder structure:

```text
frontend/public/live2d/
  live2dcubismcore.min.js
  haru/
    haru_greeter_t03.model3.json
    haru_greeter_t03.moc3
    haru_greeter_t03.pose3.json
    haru_greeter_t03.physics3.json
    haru_greeter_t03.2048/
    expressions/
    motion/
  shizuku/
    sounds/
```

If you want to switch model, update `VITE_LIVE2D_MODEL_PATH` in `frontend/.env`.
