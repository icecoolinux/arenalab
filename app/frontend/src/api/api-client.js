"use client";

import { useRouter } from 'next/navigation';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

function getToken() 
{
	if (typeof window === "undefined") return null;
	return localStorage.getItem("token");
}

function setAuthCookie(token) {
	if (typeof window !== "undefined") {
		// Set cookie for server-side middleware
		document.cookie = `auth-token=${token}; path=/; secure; samesite=strict`;
	}
}

function clearAuthCookie() {
	if (typeof window !== "undefined") {
		document.cookie = `auth-token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
	}
}

function buildUrl(path, query) 
{
	const p = path.startsWith("/") ? path : `/${path}`;
	const url = new URL(`${BASE_URL}${p}`, typeof window !== "undefined" ? window.location.origin : undefined);
	if (query && typeof query === "object") {
	Object.entries(query).forEach(([k, v]) => {
		if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
	});
	}
	return url.toString().replace("//api", "/api");
}

/**
 * api(path, options)
 * - method: GET/POST/PUT/PATCH/DELETE (default GET)
 * - body: objeto JS (se serializa como JSON) o FormData (no se toca)
 * - headers: headers extra
 * - query: objeto de query params
 * - auth: true/false agrega Authorization Bearer si hay token (default true)
 * - credentials: 'include' para cookies (si usás sesiones por cookie/CORS)
 * - timeout: ms para abortar
 */
export async function api(path, {
  method = "GET",
  body,
  headers = {},
  query,
  auth = true,
  credentials,   // 'include' | 'same-origin' | 'omit'
  timeout = 15000
} = {}) {

  const url = buildUrl(path, query);
  const token = auth ? getToken() : null;

  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(new Error("Request timeout")), timeout);

  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
  const finalHeaders = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...headers
  };

  const init = {
    method,
    headers: finalHeaders,
    signal: ctrl.signal,
    ...(credentials ? { credentials } : {}),
    ...(method !== "GET" && method !== "HEAD"
        ? { body: isFormData ? body : (body != null ? JSON.stringify(body) : undefined) }
        : {})
  };

  let res;
  try {
    res = await fetch(url, init);
  } finally {
    clearTimeout(id);
  }

  // Intenta parsear JSON; si falla, devuelve texto
  const parse = async () => {
	  if (res.status === 204) {
	    return null; // sin contenido
	  }
	  const ct = res.headers.get("content-type") || "";
	  if (ct.includes("application/json")) {
	    try { return await res.json(); } catch { return null; }
	  }
	  return await res.text();
	};

  const data = await parse();

	if (!res.ok) {
		// Unauthorized, go to login 
		if(res.status == 401)
			window.location.href = "/login";

	  const error = new Error(
	    typeof data === "string" && data?.trim() ? data : `HTTP ${res.status}`
	  );
	  error.status = res.status;
	  error.data = data;
	  error.url = url;
	  throw error;
	}

  return data;
}

/**
 * Fetch a file from the workspace via the API
 * @param {string} workspacePath - Path like "/workspace/experiments/.../config.yaml"
 * @param {object} opts - Additional options for the API call
 * @returns {Promise} The file content
 */
export const getWorkspaceFile = (workspacePath, opts={}) => 
  api('/api/workspace/' + workspacePath, { ...opts, method: "GET" });

/**
 * Enhanced login helper that sets both localStorage and cookie
 */
export const login = async (email, password) => {
	const { token } = await post("/api/auth/login", { email, password }, { auth: false });
	localStorage.setItem("token", token);
	setAuthCookie(token);
	return token;
};

/**
 * Enhanced logout helper that clears both localStorage and cookie
 */
export const logout = () => {
	localStorage.removeItem("token");
	clearAuthCookie();
	if (typeof window !== "undefined") {
		window.location.href = "/login";
	}
};

/**
 * Helpers cómodos opcionales
 */
export const get  = (path, opts={}) => api(path, { ...opts, method: "GET" });
export const post = (path, body, opts={}) => api(path, { ...opts, method: "POST", body });
export const put  = (path, body, opts={}) => api(path, { ...opts, method: "PUT", body });
export const patch= (path, body, opts={}) => api(path, { ...opts, method: "PATCH", body });
export const del  = (path, opts={}) => api(path, { ...opts, method: "DELETE" });

/**
 * API Service Functions
 */

// Experiments
export const getExperiment = (experimentId) => get(`/api/experiments/${experimentId}`);
export const getExperiments = (query = {}) => get('/api/experiments', { query });
export const createExperiment = (data) => post('/api/experiments', data);
export const checkExperimentDependencies = (experimentId) => get(`/api/experiments/${experimentId}/dependencies`);
export const deleteExperiment = (experimentId, confirmed = false) =>
  del(`/api/experiments/${experimentId}`, { query: { confirmed } });
export const updateExperimentNotes = (experimentId, notesText) =>
  put(`/api/experiments/${experimentId}/results`, null, { query: { results_text: notesText } });
export const toggleExperimentFavorite = (experimentId) => put(`/api/experiments/${experimentId}/favorite`);

// Revisions
export const getRevisions = (experimentId) =>
  experimentId ? get('/api/revisions', { query: { experiment_id: experimentId } }) : get('/api/revisions');
export const getRevision = (revisionId) => get(`/api/revisions/${revisionId}`);
export const checkRevisionDependencies = (revisionId) => get(`/api/revisions/${revisionId}/dependencies`);
export const deleteRevision = (revisionId, confirmed = false) =>
  del(`/api/revisions/${revisionId}`, { query: { confirmed } });
export const toggleRevisionFavorite = (revisionId) => put(`/api/revisions/${revisionId}/favorite`);

// Runs
export const getRuns = (params = {}) => get('/api/runs', { query: params });
export const getRun = (runId) => get(`/api/runs/${runId}`);
export const startRun = (runId) => post(`/api/runs/${runId}/run`);
export const stopRun = (runId) => post(`/api/runs/${runId}/stop`);
export const restartRun = (runId) => post(`/api/runs/${runId}/restart`);
export const checkRunDependencies = (runId) => get(`/api/runs/${runId}/dependencies`);
export const deleteRun = (runId, confirmed = false) =>
  del(`/api/runs/${runId}`, { query: { confirmed } });
export const updateRunNotes = (runId, notesText) =>
  put(`/api/runs/${runId}/results`, null, { query: { results_text: notesText } });
export const toggleRunFavorite = (runId) => put(`/api/runs/${runId}/favorite`);
export const getRunLogs = (runId) => get(`/api/runs/${runId}/logs`);
export const checkTensorboardStatus = (runId) => get(`/api/runs/${runId}/tensorboard/status`);

// Plugins
export const getPlugins = (scope) => get('/api/plugins', { query: scope ? { scope } : {} });
export const getPluginExecutions = (targetId, scope = 'experiment') =>
  get('/api/plugins/executions', { query: { target_id: targetId, scope } });
export const startPlugin = (pluginName, targetId, scope, settings = {}) =>
  post('/api/plugins/execute', { plugin_name: pluginName, target_id: targetId, scope, settings });
export const stopPlugin = (executionId) => post(`/api/plugins/executions/${executionId}/stop`);
export const getPluginNotes = (targetId, scope) =>
  get('/api/plugins/notes', { query: { target_id: targetId, scope } });

// Environments
export const getEnvironments = () => get('/api/environments');
export const checkEnvironmentDependencies = (environmentId) => get(`/api/environments/${environmentId}/dependencies`);
export const deleteEnvironment = (environmentId, confirmed = false) =>
  del(`/api/environments/${environmentId}`, { query: { confirmed } });
