import { Suspense } from "react";
import { InterviewFlow } from "@/components/interview/interview-flow";
import { Loading } from "@/components/interview/loading";

export default function InterviewPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  return (
    <Suspense fallback={<Loading />}>
      <InterviewContent params={params} />
    </Suspense>
  );
}

async function InterviewContent({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <InterviewFlow token={token} />;
}
