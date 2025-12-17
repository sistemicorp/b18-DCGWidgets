"""
Minimal Example to test widgets

"""
import asyncio
import dearcygui as dcg
from dearcygui.utils.asyncio_helpers import AsyncPoolExecutor, run_viewport_loop
from test_stats import build_viewport_menu_bar


def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    C = dcg.Context()
    C.queue = AsyncPoolExecutor(loop=loop)

    C.viewport.wait_for_input = True
    C.viewport.initialize(title="My App", width=900, height=600)

    build_viewport_menu_bar(C)

    with dcg.Window(C, label="Main", primary=True):
        dcg.Text(C, value="Now showing CPU, FPS, and Max FPS in the viewport menu bar.")

    try:
        loop.run_until_complete(run_viewport_loop(C.viewport))
    finally:
        C.running = False
        C.queue.shutdown()
        C.viewport.destroy()
        loop.stop()
        loop.close()


if __name__ == "__main__":
    main()
