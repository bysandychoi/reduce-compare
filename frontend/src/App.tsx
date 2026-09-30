import { useEffect, useState } from "react";

type ConnectionState =
  | { status: "loading" }
  | { status: "connected"; version: string }
  | { status: "unavailable" };

function isHealthResponse(value: unknown): value is { status: "ok"; version: string } {
  if (typeof value !== "object" || value === null) return false;
  const health = value as Record<string, unknown>;
  return health.status === "ok" && typeof health.version === "string";
}

export default function App() {
  const [connection, setConnection] = useState<ConnectionState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    async function checkBackend() {
      try {
        const response = await fetch("/api/health", { signal: controller.signal });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const health: unknown = await response.json();
        if (!isHealthResponse(health)) throw new Error("Invalid health response");
        setConnection({ status: "connected", version: health.version });
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setConnection({ status: "unavailable" });
        }
      }
    }

    void checkBackend();
    return () => controller.abort();
  }, []);

  const connectionText =
    connection.status === "connected"
      ? `백엔드 연결됨 · API ${connection.version}`
      : connection.status === "unavailable"
        ? "백엔드에 연결할 수 없습니다"
        : "백엔드 연결 확인 중…";

  return (
    <main className="shell">
      <h1>Reduce &amp; Compare</h1>
      <p className="sub">대규모 표 데이터 축소 · 유사도 확인</p>
      <p className={`connection connection--${connection.status}`} role="status" aria-live="polite">
        <span className="connection__dot" aria-hidden="true" />
        {connectionText}
      </p>
      <p className="note">
        화면은 백로그 순서대로 채웁니다. 다음 단계: 폴더 선택 화면과 처리 흐름을 연결합니다.
      </p>
    </main>
  );
}
