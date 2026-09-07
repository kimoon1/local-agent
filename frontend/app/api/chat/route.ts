import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";

export async function POST(request: NextRequest) {
  try {
    const response = await fetch(`${API_URL}/api/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: await request.text() });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ error: "FastAPI 백엔드에 연결할 수 없습니다. 서버가 8000 포트에서 실행 중인지 확인하세요." }, { status: 503 });
  }
}
