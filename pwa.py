"""
pwa.py
Makes the app installable on phones/tablets: injects a <link rel="manifest">,
a theme-color meta tag, an apple-touch-icon, and registers a service worker.
Once deployed, opening the app's URL in a phone/tablet browser and choosing
"Add to Home Screen" (Safari) or "Install app" (Chrome) creates a home-screen
icon that opens the app in its own standalone window, like a normal app.

Requires:
  - .streamlit/config.toml with [server] enableStaticServing = true
  - a top-level static/ folder containing manifest.json, service-worker.js,
    icon-192.png, icon-512.png

This does NOT make the app work offline — it still needs a live connection
to the Streamlit server, same as before. It only affects how it looks and
launches once installed.
"""

import streamlit.components.v1 as components


def inject_pwa():
    components.html(
        """
        <script>
        (function() {
            const doc = window.parent.document;

            if (!doc.querySelector('link[rel="manifest"]')) {
                const link = doc.createElement('link');
                link.rel = 'manifest';
                link.href = 'app/static/manifest.json';
                doc.head.appendChild(link);
            }
            if (!doc.querySelector('meta[name="theme-color"]')) {
                const meta = doc.createElement('meta');
                meta.name = 'theme-color';
                meta.content = '#1f77b4';
                doc.head.appendChild(meta);
            }
            if (!doc.querySelector('link[rel="apple-touch-icon"]')) {
                const icon = doc.createElement('link');
                icon.rel = 'apple-touch-icon';
                icon.href = 'app/static/icon-192.png';
                doc.head.appendChild(icon);
            }
            if ('serviceWorker' in navigator) {
                navigator.serviceWorker.register('app/static/service-worker.js').catch(function(err) {
                    console.log('Service worker registration skipped:', err);
                });
            }
        })();
        </script>
        """,
        height=0,
        width=0,
    )
