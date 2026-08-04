# Z-Image Turbo benchmark (Track D)

Prompt: _a realistic full-body fashion photograph of a woman in her mid-20s wearing a casual tank top and denim shorts, standing outdoors in a sunny park, natural daylight, photorealistic, sharp focus, highly detailed, professional photography_

Settings: 8 steps, cfg 1.0, euler/simple, seed 42. Encoder warm across runs (first = cold incl. 5.3GB qwen3 load).

| model | resolution | phase | VRAM peak | wall time | ok | output |
|---|---|---|---|---|---|---|
| Z-Image Q4_K_M | 512x512 | cold | 2129 MB | 187.8 s | True | z_image_turbo_00002_.png |
| Z-Image Q4_K_M | 768x768 | warm | 2785 MB | 202.1 s | True | z_image_turbo_00003_.png |
| Z-Image Q4_K_M | 1024x1024 | warm | 3785 MB | 424.1 s | True | z_image_turbo_00004_.png |
| Z-Image Q3_K_S | 512x512 | warm | 2127 MB | 272.4 s | True | z_image_turbo_00005_.png |
| Z-Image Q3_K_S | 768x768 | warm | 2785 MB | 204.4 s | True | z_image_turbo_00006_.png |
| Z-Image Q3_K_S | 1024x1024 | warm | 3785 MB | 426.3 s | True | z_image_turbo_00007_.png |
