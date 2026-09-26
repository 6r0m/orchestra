// The page's one way to its server: every request carries the page's token, and a refusal comes back as
// an Error carrying the server's own words.

export const CONFIG = JSON.parse(document.getElementById("config").textContent);

export async function api(path, body) {
  const options = { headers: { "X-Workbench-Token": CONFIG.token } };
  if (body !== undefined) {
    options.method = "POST";
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({ error: response.statusText }));
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}
