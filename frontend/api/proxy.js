const BACKEND_ORIGIN = "https://backend-five-hazel-13.vercel.app";

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return chunks.length ? Buffer.concat(chunks) : undefined;
}

module.exports = async function handler(req, res) {
  const path = typeof req.query.path === "string" ? req.query.path : "";
  const original = new URL(req.url, "https://obrinexcrm.vercel.app");
  original.searchParams.delete("path");
  const query = original.searchParams.toString();
  const target = `${BACKEND_ORIGIN}/api/${path}${query ? `?${query}` : ""}`;

  const headers = { ...req.headers };
  delete headers.host;
  delete headers["content-length"];
  delete headers["x-forwarded-host"];
  delete headers["x-forwarded-proto"];

  try {
    const upstream = await fetch(target, {
      method: req.method,
      headers,
      body: ["GET", "HEAD"].includes(req.method) ? undefined : await readBody(req),
      redirect: "manual",
    });

    res.statusCode = upstream.status;
    res.setHeader("cache-control", "no-store, max-age=0");
    res.setHeader("pragma", "no-cache");
    res.setHeader("expires", "0");
    upstream.headers.forEach((value, key) => {
      if (!["cache-control", "content-encoding", "content-length", "expires", "pragma", "transfer-encoding", "set-cookie"].includes(key.toLowerCase())) {
        res.setHeader(key, value);
      }
    });

    if (typeof upstream.headers.getSetCookie === "function") {
      const cookies = upstream.headers.getSetCookie();
      if (cookies.length) res.setHeader("set-cookie", cookies);
    } else {
      const combinedCookie = upstream.headers.get("set-cookie");
      if (combinedCookie) {
        res.setHeader("set-cookie", combinedCookie.split(/,\s*(?=[^;,]+=)/));
      }
    }

    res.end(Buffer.from(await upstream.arrayBuffer()));
  } catch (error) {
    res.statusCode = 502;
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ detail: "API proxy could not reach the backend" }));
  }
};
