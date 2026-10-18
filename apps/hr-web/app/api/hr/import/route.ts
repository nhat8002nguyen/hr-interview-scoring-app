import { type NextRequest } from "next/server";
import { jsonResult } from "@/lib/api/handler";
import { problemResponse } from "@/lib/api/error";
import type { ImportSummary } from "@/lib/contracts/types";

export async function POST(request: NextRequest) {
  const incoming = await request.formData();
  const file = incoming.get("file");

  if (!(file instanceof File)) {
    return problemResponse(422, "Missing file field");
  }

  const formData = new FormData();
  formData.append("file", file, file.name);

  return jsonResult((client) =>
    client.request<ImportSummary>("POST", "/hr/import", { formData }),
  );
}
