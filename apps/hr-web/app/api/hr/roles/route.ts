import { jsonResult } from "@/lib/api/handler";
import type { Role } from "@/lib/contracts/types";

export async function GET() {
  return jsonResult((client) => client.request<Role[]>("GET", "/hr/roles"));
}
