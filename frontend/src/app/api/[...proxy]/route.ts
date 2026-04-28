import { NextRequest, NextResponse } from "next/server";

const INTERNAL = process.env.INTERNAL_API_URL || "http://localhost:1000";

async function handler(req: NextRequest): Promise<NextResponse> {
  const { pathname, search } = req.nextUrl;
  const target = `${INTERNAL}${pathname}${search}`;

  const headers = new Headers();
  const auth = req.headers.get("authorization");
  if (auth) headers.set("authorization", auth);
  const ct = req.headers.get("content-type");
  if (ct) headers.set("content-type", ct);
  const accept = req.headers.get("accept");
  if (accept) headers.set("accept", accept);

  let body: BodyInit | undefined;
  if (!["GET", "HEAD"].includes(req.method)) {
    body = await req.arrayBuffer();
  }

  const res = await fetch(target, {
    method: req.method,
    headers,
    body,
    redirect: "follow",
  });

  const resHeaders = new Headers();
  const resCt = res.headers.get("content-type");
  if (resCt) resHeaders.set("content-type", resCt);
  const cd = res.headers.get("content-disposition");
  if (cd) resHeaders.set("content-disposition", cd);

  return new NextResponse(res.body, {
    status: res.status,
    headers: resHeaders,
  });
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
