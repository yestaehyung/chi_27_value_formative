// 데모 대화 화면 — 참가자 화면과 같은 E UI지만 `study` 없이 렌더한다.
// study를 안 넘기면 VariantSession의 스터디 생명주기(과제 전/후 설문, 기준별 검증,
// 마치기 확인, 완료 화면)가 전부 꺼진다 — 추천 결과만 보면 되는 데모의 목적에 맞다.
import VariantSession from "@/components/study/VariantSession";

export default function DemoSessionPage({ params }: { params: { sessionId: string } }) {
  return <VariantSession sessionId={params.sessionId} variant="e" />;
}
