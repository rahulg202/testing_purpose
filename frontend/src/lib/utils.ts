import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge Tailwind CSS classes with clsx.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Format a date string for display.
 */
export function formatDate(dateStr: string | undefined | null): string {
  if (!dateStr) return '—';
  try {
    return new Intl.DateTimeFormat('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(dateStr));
  } catch {
    return dateStr;
  }
}

/**
 * Demo tenant. Every request is tenant-scoped by construction, so the header
 * is sent on all calls rather than being inferred server-side.
 */
export const TENANT_ID = 'acme_pharma';

/** Acting user, recorded against every audit event. */
export const ACTOR_ID = 'demo_reviewer';

/**
 * API client helper.
 */
export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'x-tenant-id': TENANT_ID,
      'x-actor-id': ACTOR_ID,
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      body?.detail || body?.error?.message || `Request failed: ${res.status}`,
    );
  }

  return res.json();
}

/** Title-case a snake_case enum value for display. */
export function humanise(value: string | null | undefined): string {
  if (!value) return '—';
  return value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
