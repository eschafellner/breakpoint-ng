/**
 * Breakpoint-NG PWA Client Integration
 * - Service Worker Registration
 * - Install Prompt Banner (Android/Desktop & iOS Safari Guide)
 */

(function () {
  'use strict';

  // 1. Service Worker Registration
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register('/sw.js', { scope: '/' })
        .then((registration) => {
          if (registration.active) registration.active.postMessage({ type: 'REFRESH_OFFLINE' });
          registration.addEventListener('updatefound', () => {
            const newWorker = registration.installing;
            if (newWorker) {
              newWorker.addEventListener('statechange', () => {
                if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                  // New update available
                  console.info('Breakpoint-NG update ready. Reload to view changes.');
                }
              });
            }
          });
        })
        .catch((error) => {
          console.warn('Breakpoint-NG: SW registration failed', error);
        });
    });
  }

  // 2. Install Banner Handling
  window.addEventListener('online', () => {
    navigator.serviceWorker?.controller?.postMessage({ type: 'REFRESH_OFFLINE' });
  });

  const STORAGE_KEY = 'breakpoint_pwa_prompt_dismissed';
  let deferredPrompt = null;

  // Determine if already running as installed PWA
  const isStandalone =
    window.matchMedia('(display-mode: standalone)').matches ||
    window.navigator.standalone === true;

  if (isStandalone) {
    return; // Already installed, do not show any banner
  }

  // Check dismissal preference (valid for 14 days)
  let dismissedTime = null;
  try { dismissedTime = localStorage.getItem(STORAGE_KEY); } catch (_) {}
  if (dismissedTime && Date.now() - parseInt(dismissedTime, 10) < 14 * 24 * 60 * 60 * 1000) {
    return;
  }

  function dismissBanner() {
    const banner = document.getElementById('pwaInstallBanner');
    if (banner) {
      banner.style.display = 'none';
    }
    try { localStorage.setItem(STORAGE_KEY, Date.now().toString()); } catch (_) {}
  }

  function renderBanner(options) {
    if (document.getElementById('pwaInstallBanner')) return;

    const banner = document.createElement('div');
    banner.id = 'pwaInstallBanner';
    banner.className = 'pwa-install-banner';
    banner.setAttribute('role', 'region');
    banner.setAttribute('aria-label', 'App Installation');

    banner.innerHTML = `
      <div class="pwa-banner-content">
        <div class="pwa-banner-icon">
          <img src="/static/icons/icon-192x192.png" width="36" height="36" alt="App Icon">
        </div>
        <div class="pwa-banner-text">
          <strong>${options.title}</strong>
          <span>${options.description}</span>
        </div>
        <div class="pwa-banner-actions">
          ${options.actionBtn ? options.actionBtn : ''}
          <button type="button" class="btn-close-pwa" id="pwaDismissBtn" aria-label="Schließen">✕</button>
        </div>
      </div>
    `;

    document.body.appendChild(banner);

    document.getElementById('pwaDismissBtn')?.addEventListener('click', dismissBanner);

    if (options.onAttach) {
      options.onAttach(banner);
    }
  }

  // A. Native 'beforeinstallprompt' (Chrome, Edge, Android)
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;

    renderBanner({
      title: 'Als App installieren',
      description: 'Schneller Zugriff auf Platzbuchungen & Club-Infos direkt auf deinem Startbildschirm.',
      actionBtn: '<button type="button" class="btn sm court" id="pwaInstallBtn">Installieren</button>',
      onAttach: () => {
        document.getElementById('pwaInstallBtn')?.addEventListener('click', async () => {
          if (!deferredPrompt) return;
          deferredPrompt.prompt();
          const { outcome } = await deferredPrompt.userChoice;
          if (outcome === 'accepted') {
            dismissBanner();
          }
          deferredPrompt = null;
        });
      }
    });
  });

  // B. iOS Safari Instruction (Manual add to home screen)
  const isIos = /iphone|ipad|ipod/.test(window.navigator.userAgent.toLowerCase());
  const isSafari =
    /safari/.test(window.navigator.userAgent.toLowerCase()) &&
    !/chrome|crios|fxios/.test(window.navigator.userAgent.toLowerCase());

  if (isIos && isSafari) {
    // Show iOS tip after 3 seconds of browsing
    window.addEventListener('load', () => {
      setTimeout(() => {
        if (!document.getElementById('pwaInstallBanner')) {
          renderBanner({
            title: 'App zum Startbildschirm hinzufügen',
            description: 'Tippe in Safari auf <strong>Teilen</strong> <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-2px"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"></path><polyline points="16 6 12 2 8 6"></polyline><line x1="12" y1="2" x2="12" y2="15"></line></svg> und wähle <em>"Zum Home-Bildschirm"</em>.',
            actionBtn: ''
          });
        }
      }, 3000);
    });
  }

  // Handle successful installation
  window.addEventListener('appinstalled', () => {
    console.info('Breakpoint-NG: App wurde erfolgreich installiert.');
    dismissBanner();
  });
})();
