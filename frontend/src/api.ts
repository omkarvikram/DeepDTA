
const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  'https://deep-dta-b1bg.vercel.app'
).replace(/\/$/, '');

export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}/api${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'X-Research-Client': 'web',
      ...(options.body && !(options.body instanceof FormData)
        ? { 'Content-Type': 'application/json' }
        : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    let error: any;
    try {
      error = await response.json();
    } catch {
      error = { detail: 'The server could not complete this request.' };
    }
    throw new Error(
      typeof error.detail === 'string'
        ? error.detail
        : JSON.stringify(error.detail)
    );
  }

  return response.json();
}

export const post = (path: string, body: any = {}) =>
  api(path, { method: 'POST', body: JSON.stringify(body) });

export async function download(path: string, filename: string, body?: any) {
  const response = await fetch(`${API_BASE}/api${path}`, {
    method: body ? 'POST' : 'GET',
    credentials: 'include',
    headers: {
      'X-Research-Client': 'web',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const e = await response.json();
    throw new Error(e.detail || 'Download failed.');
  }

  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export type Prediction = {
  id: string;
  drug_name: string;
  protein_name: string;
  smiles: string;
  sequence: string;
  dataset: string;
  score: number;
  created_at: string;
  model_version: string;
  provenance: any;
  strength_guide?: {
    label: string;
    band: 'weak' | 'moderate' | 'strong' | 'unknown';
    explanation: string;
    basis: string;
    caution: string;
    source: string;
  };
};
