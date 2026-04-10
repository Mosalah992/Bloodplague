/** Build a concise message from a failed fetch, including FastAPI `detail` when present. */
async function errorMessageFromResponse(response) {
  const statusLine = `${response.status} ${response.statusText}`;
  let bodyText = "";
  try {
    bodyText = await response.text();
  } catch {
    return statusLine;
  }
  const trimmed = bodyText.trim();
  if (!trimmed) return statusLine;

  try {
    const data = JSON.parse(trimmed);
    if (typeof data.detail === "string") {
      return `${statusLine} :: ${data.detail}`;
    }
    if (Array.isArray(data.detail)) {
      const parts = data.detail.map((item) =>
        typeof item === "string" ? item : item?.msg ?? JSON.stringify(item)
      );
      return `${statusLine} :: ${parts.join("; ")}`;
    }
    if (data.detail != null) {
      return `${statusLine} :: ${String(data.detail)}`;
    }
    if (typeof data.message === "string") {
      return `${statusLine} :: ${data.message}`;
    }
  } catch {
    /* not JSON */
  }

  const snippet = trimmed.length > 240 ? `${trimmed.slice(0, 240)}...` : trimmed;
  return `${statusLine} :: ${snippet}`;
}

export async function fetchJson(path, options = {}) {
  const headers = { ...(options.headers || {}) };

  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(path, {
    ...options,
    headers
  });

  if (!response.ok) {
    throw new Error(await errorMessageFromResponse(response));
  }

  return response.json();
}
