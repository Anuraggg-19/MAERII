export async function request(
  url,
  { body, signal, method, timeout = 180000 } = {},
) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  signal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(abort, timeout);
  try {
    const response = await fetch(url, {
      method: method || (body === undefined ? "GET" : "POST"),
      credentials: "same-origin",
      signal: controller.signal,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const messages = {
        401: "Your session expired. Refresh the page and reopen the material.",
        403: "This information is unavailable in your current session. Reopen the material.",
        422: "Please check your choices and try again.",
        429: "The usage limit has been reached. Please try again later.",
        503: "This service is temporarily unavailable. Please try again shortly.",
      };
      const error = new Error(
        messages[response.status] ||
          "The request could not be completed. Please try again.",
      );
      error.status = response.status;
      throw error;
    }
    if (!data || typeof data !== "object")
      throw new Error(
        "The server returned an unreadable response. Please try again.",
      );
    return { data, ref: response.headers.get("x-maerii-assistant-context") };
  } catch (error) {
    if (error.name === "AbortError" && !signal?.aborted)
      throw new Error(
        "This request took too long. It may still be processing; check before retrying.",
      );
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}
export async function assistantRequest(path, body, signal) {
  return (
    await request("/api/assistant/" + path, { body, signal, timeout: 45000 })
  ).data;
}
