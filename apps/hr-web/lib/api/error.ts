import { NextResponse } from "next/server";
import type { ProblemDetails } from "@/lib/contracts/types";

const TITLES: Record<number, string> = {
  400: "Bad Request",
  401: "Unauthorized",
  403: "Forbidden",
  404: "Not Found",
  409: "Conflict",
  413: "Payload Too Large",
  422: "Unprocessable Entity",
};

export function problemResponse(status: number, detail: string): NextResponse {
  const body: ProblemDetails = {
    type: "about:blank",
    title: TITLES[status] ?? "Error",
    status,
    detail,
  };
  return NextResponse.json(body, { status });
}
