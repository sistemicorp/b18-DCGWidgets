import asyncio
import psutil
import dearcygui as dcg


def build_viewport_menu_bar(C: dcg.Context) -> None:
    """One viewport menu bar: left-side menus + right-side CPU/FPS/MaxFPS."""
    def request_exit(*_args, **_kwargs) -> None:
        C.running = False
        C.viewport.wake()

    with dcg.MenuBar(C, parent=C.viewport) as bar:
        # ----- Left side: your menus -----
        with dcg.Menu(C, label="File"):
            dcg.MenuItem(C, label="Exit", callback=request_exit)

        with dcg.Menu(C, label="Help"):
            dcg.MenuItem(C, label="About", callback=lambda *_: print("About clicked"))

        # ----- Right side: stats -----
        with dcg.HorizontalLayout(C, alignment_mode=dcg.Alignment.RIGHT, no_wrap=True):
            cpu_bar = dcg.ProgressBar(C, value=0.0, overlay="CPU 0%", width="0.07*bar.width")
            dcg.Spacer(C, width="0.01*bar.width")

            fps_bar = dcg.ProgressBar(C, value=0.0, overlay="FPS 0", width="0.07*bar.width")
            dcg.Spacer(C, width="0.01*bar.width")

            max_fps_bar = dcg.ProgressBar(C, value=0.0, overlay="Max 0", width="0.07*bar.width")

    async def cpu_loop() -> None:
        proc = psutil.Process()
        proc.cpu_percent(None)  # prime
        while C.running:
            cpu = proc.cpu_percent(None)
            cpu_bar.value = max(0.0, min(cpu / 100.0, 1.0))
            cpu_bar.overlay = f"CPU {int(cpu)}%"
            C.viewport.wake()
            await asyncio.sleep(1.0)

    async def fps_loop() -> None:
        last_fc = C.viewport.metrics.frame_count
        last_t = C.viewport.metrics.last_time_after_swapping
        while C.running:
            fc = C.viewport.metrics.frame_count
            t = C.viewport.metrics.last_time_after_swapping
            dt = max(1e-6, (t - last_t))
            fps = (fc - last_fc) / dt

            fps_bar.value = max(0.0, min(fps / 120.0, 1.0))
            fps_bar.overlay = f"FPS {int(fps)}"

            last_fc, last_t = fc, t
            C.viewport.wake()
            await asyncio.sleep(0.25)

    async def max_fps_loop() -> None:
        """
        Estimate maximum achievable FPS for rendering (when frames *are* being rendered).
        This averages the last N frame render durations.

        Note: if the app is idle and skipping frames (wait_for_input=True),
        this loop waits until frames advance.
        """
        last_fc = C.viewport.metrics.frame_count

        while C.running:
            acc_dt = 0.0
            acc_n = 0

            # Collect ~30 rendered frames (or fewer if the app is shutting down)
            while acc_n < 30 and C.running:
                fc = C.viewport.metrics.frame_count
                if fc == last_fc:
                    # No frame rendered yet (idle) -> wait a bit
                    await asyncio.sleep(0.05)
                    continue

                last_fc = fc
                m = C.viewport.metrics
                frame_dt = m.last_time_after_swapping - m.last_time_before_event_handling
                acc_dt += max(1e-6, frame_dt)
                acc_n += 1

                # Small delay to avoid busy-looping
                await asyncio.sleep(0.01)

            avg_dt = acc_dt / max(1, acc_n)
            max_fps = 1.0 / max(1e-6, avg_dt)

            max_fps_bar.value = max(0.0, min(max_fps / 120.0, 1.0))
            max_fps_bar.overlay = f"Max {int(max_fps)}"
            C.viewport.wake()

            # Recompute periodically (not every frame)
            await asyncio.sleep(0.5)

    # Submit background tasks
    C.queue.submit(cpu_loop)
    C.queue.submit(fps_loop)
    C.queue.submit(max_fps_loop)
