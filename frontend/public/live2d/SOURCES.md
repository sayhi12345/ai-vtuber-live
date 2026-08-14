# Live2D Asset Sources

- Haru (receptionist version, `haru_greeter_t05`) model assets were downloaded from the
  official Live2D sample data collection:
  - Page: `https://www.live2d.com/en/learn/sample/haru-receptionist/`
  - Zip: `https://cubism.live2d.com/sample-data/bin/haru_greeter/haru_greeter_ja.zip`
  - Only the `runtime/` folder is committed; the zip also contains the `.cmo3`/`.can3`
    editor sources and layered PSDs if model edits are ever needed.
- Expression files (`expressions/F01–F08.exp3.json`) and the Rongrong texture variants
  (`texture_0x_rongrong.png`) predate this download and are carried over from the
  previous `haru_greeter_t03` assets (`https://cdn.jsdelivr.net/gh/guansss/pixi-live2d-display/test/assets/haru/`).
  The t03 and t05 texture atlases are pixel-identical, so the Rongrong textures apply as-is.
- Shizuku sound files were downloaded from:
  - `https://cdn.jsdelivr.net/gh/guansss/pixi-live2d-display/test/assets/shizuku/sounds/`
- Cubism Core runtime was downloaded from:
  - `https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js`

Refer to:

- Live2D Free Material License terms (commercial use allowed for general users and
  small-scale enterprises with annual sales under 10M JPY; mid/large enterprises are
  limited to closed testing): `https://www.live2d.com/en/terms/live2d-free-material-license-agreement/`
