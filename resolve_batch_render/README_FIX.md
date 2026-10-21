# resolve_batch_render feed-transcode fix (2026-10-21)

Production path: `/home/tovgrishkoff/resolve_batch_render`

## Root cause
1. `reels-autopost` and `yt-autopost` share `./output` and both used temp name `.CRUISE__POOL.{pid}.mp4`.
   Inside Docker the Python process is PID 1 → both wrote `.CRUISE__POOL.1.mp4`.
2. 10-bit HEVC (~50 Mbps, 228 MB / 37s) with `-threads 2` SIGKILL/timeout under the shared 512m cgroup.
3. Secondary: Instagram error path referenced `ig_caption` before assignment.

## Fix
- Unique temp names (`host.pid.uuid`) + `fcntl` exclusive lock per reel.
- OOM-safe ffmpeg (`-threads 1`, x264 `threads=1`), skip scale/fps when already 1080x1920.
- Raise `reels-autopost` / `yt-autopost` to 768m.
- Initialize `ig_caption = ""` before the Instagram try-block (applied live in `uploader/main.py`).

Files mirrored here for review; deploy is the live volume-mounted directory + compose recreate.

## Verification (2026-10-21)

- Feed file: `output/publish_ready/CRUISE__POOL.mp4` (122 MB, h264 1080x1920 + aac).
- YouTube: **posted** `vjxys6VAVBU`.
- Pinterest: **posted**.
- Instagram: first account published (`media_id=18124532362870923`), staggering to second account.
- Containers `reels-autopost` / `yt-autopost` / `pinterest-autopost` recreated with the fix.
