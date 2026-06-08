import { NextRequest } from "next/server";

const BACKEND = process.env.BACKEND_URL || "http://backend:8000";

export const maxDuration = 120;

async function proxy(req: NextRequest) {
  const url = new URL(req.url);
  const path = url.pathname.replace(/^\/api/, "");
  const target = `${BACKEND}${path}${url.search}`;

  const headers = new Headers();
  req.headers.forEach((v, k) => {
    if (k.toLowerCase() !== "host") headers.set(k, v);
  });

  const init: RequestInit = {
    method: req.method,
    headers,
    // @ts-expect-error - duplex required for streaming request body
    duplex: "half",
  };

  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = req.body;
  }

  const resp = await fetch(target, init);

  const respHeaders = new Headers();
  resp.headers.forEach((v, k) => {
    if (!["transfer-encoding", "content-encoding"].includes(k.toLowerCase())) {
      respHeaders.set(k, v);
    }
  });

  return new Response(resp.body, {
    status: resp.status,
    statusText: resp.statusText,
    headers: respHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const PATCH = proxy;
