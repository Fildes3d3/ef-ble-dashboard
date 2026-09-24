// Every call to the server goes through here.

export const fetchJson = async (url, options) => {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Request failed.");
  return data;
};


export const getStatus = () => fetchJson("/api/status");
export const getHistory = (device) => fetchJson(`/api/history?device=${device}`);
export const getSession = () => fetchJson("/api/auth/me");
export const getHealth = () => fetch("/health").then(response => response.json());

export const signIn = (password) =>
  fetchJson("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });

export const signOut = () => fetchJson("/api/auth/logout", { method: "POST" });

export const requestRefresh = (device) =>
  fetchJson(`/api/refresh?device=${device}`, { method: "POST" });

export const writeControl = (key, value) =>
  fetchJson(`/api/control/${key}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
