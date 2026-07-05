#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: postprocess_flutter_web.py <build_web_dir> <build_id>",
            file=sys.stderr,
        )
        return 1

    root = Path(sys.argv[1]).resolve()
    build_id = sys.argv[2].strip()
    if not build_id:
        print("build_id must not be empty", file=sys.stderr)
        return 1

    index = root / "index.html"
    bootstrap = root / "flutter_bootstrap.js"
    service_worker = root / "flutter_service_worker.js"

    if index.exists():
        text = index.read_text()
        text = re.sub(
            r'src="flutter_bootstrap\.js(\?v=[^"]+)?"',
            f'src="flutter_bootstrap.js?v={build_id}"',
            text,
        )
        text = re.sub(
            r"script\.src = 'flutter_bootstrap\.js(\?v=[^']+)?';",
            f"script.src = 'flutter_bootstrap.js?v={build_id}';",
            text,
        )
        index.write_text(text)

    if bootstrap.exists():
        js = bootstrap.read_text()
        js = js.replace('c("main.dart.js")', f'c("main.dart.js?v={build_id}")')
        js = js.replace(
            '"mainJsPath":"main.dart.js"',
            f'"mainJsPath":"main.dart.js?v={build_id}"',
        )
        bootstrap.write_text(js)

    # Replace any legacy Flutter worker with a cleanup worker so existing
    # clients drop stale caches and unregister themselves on next visit.
    service_worker.write_text(
        f"""const GLAME_SW_BUILD_ID = "{build_id}";

self.addEventListener("install", (event) => {{
  self.skipWaiting();
}});

self.addEventListener("activate", (event) => {{
  event.waitUntil((async () => {{
    const keys = await caches.keys();
    await Promise.all(
      keys
        .filter((key) => key.startsWith("flutter-"))
        .map((key) => caches.delete(key)),
    );
    await self.registration.unregister();
    const clients = await self.clients.matchAll({{
      type: "window",
      includeUncontrolled: true,
    }});
    await Promise.all(clients.map((client) => client.navigate(client.url)));
  }})());
}});

self.addEventListener("fetch", () => {{}});
""",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
