'use client';

import { useEffect } from 'react';

const RELOAD_MARKER = 'glame:stale-deployment-reload';

function isStaleChunkError(value: unknown): boolean {
  const message =
    value instanceof Error
      ? `${value.name} ${value.message}`
      : typeof value === 'string'
        ? value
        : value && typeof value === 'object' && 'message' in value
          ? String((value as { message?: unknown }).message)
          : '';

  return (
    message.includes('ChunkLoadError') ||
    message.includes('Loading chunk') ||
    message.includes('Failed to load chunk') ||
    message.includes('dynamically imported module')
  );
}

function reloadOnce() {
  try {
    if (sessionStorage.getItem(RELOAD_MARKER) === '1') {
      return;
    }
    sessionStorage.setItem(RELOAD_MARKER, '1');
  } catch {
    // If storage is unavailable, a single reload is still the safest recovery.
  }

  window.location.reload();
}

export default function StaleDeploymentReloader() {
  useEffect(() => {
    try {
      sessionStorage.removeItem(RELOAD_MARKER);
    } catch {
      // No-op.
    }

    const onError = (event: ErrorEvent) => {
      if (isStaleChunkError(event.error) || isStaleChunkError(event.message)) {
        reloadOnce();
      }
    };

    const onUnhandledRejection = (event: PromiseRejectionEvent) => {
      if (isStaleChunkError(event.reason)) {
        reloadOnce();
      }
    };

    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onUnhandledRejection);

    return () => {
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onUnhandledRejection);
    };
  }, []);

  return null;
}
