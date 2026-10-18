import { getInterview, submitAudioAnswer, submitTextAnswer } from "@/lib/api";

function jsonResponse(
  body: unknown,
  init: { ok?: boolean; status?: number } = {},
): Response {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => body,
  } as unknown as Response;
}

function headersOf(init: RequestInit | undefined): Record<string, string> {
  return init?.headers as Record<string, string>;
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

it("getInterview sends the token header and returns the interview", async () => {
  const data = {
    candidate: { id: 1, name: "Nhi", role: "Backend Engineer" },
    questions: [],
    progress: { answered: 0, total: 6 },
  };
  fetchMock.mockResolvedValue(jsonResponse(data));
  const result = await getInterview("tok123");
  expect(fetchMock).toHaveBeenCalledWith(
    "http://api.test/candidate/interview",
    { headers: { "X-Candidate-Token": "tok123" } },
  );
  expect(result).toEqual(data);
});

it("submitTextAnswer posts JSON with answer_type and text", async () => {
  fetchMock.mockResolvedValue(
    jsonResponse({
      status: "received",
      unchanged: false,
      answer: { answer_type: "text", version: 1, submitted_at: "t" },
    }),
  );
  await submitTextAnswer("tok", 1, "my answer");
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("http://api.test/candidate/interview/answers/1");
  expect(init?.method).toBe("POST");
  expect(headersOf(init)["X-Candidate-Token"]).toBe("tok");
  expect(JSON.parse(init?.body as string)).toEqual({
    answer_type: "text",
    text: "my answer",
  });
});

it("submitAudioAnswer posts a FormData body with the file and no manual Content-Type", async () => {
  fetchMock.mockResolvedValue(
    jsonResponse({
      status: "received",
      unchanged: false,
      answer: { answer_type: "audio", version: 1, submitted_at: "t" },
    }),
  );
  const file = new File(["x"], "a.m4a", { type: "audio/mp4" });
  await submitAudioAnswer("tok", 2, file);
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("http://api.test/candidate/interview/answers/2/audio");
  const body = init?.body as FormData;
  expect(body).toBeInstanceOf(FormData);
  expect(body.get("file")).toBe(file);
  expect(headersOf(init)["Content-Type"]).toBeUndefined();
});

it("throws ApiError with status and detail on a non-2xx JSON body", async () => {
  fetchMock.mockResolvedValue(
    jsonResponse({ detail: "text is empty" }, { ok: false, status: 422 }),
  );
  await expect(getInterview("tok")).rejects.toMatchObject({
    status: 422,
    detail: "text is empty",
  });
});

it("throws ApiError without detail on a non-JSON error body", async () => {
  fetchMock.mockResolvedValue({
    ok: false,
    status: 500,
    json: async () => {
      throw new Error("not json");
    },
  } as unknown as Response);
  await expect(getInterview("tok")).rejects.toMatchObject({ status: 500 });
});
