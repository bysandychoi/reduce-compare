import { useEffect, useState, type MouseEvent, type ReactNode } from "react";

import UploadPage from "./UploadPage";
import ResultsPage from "./ResultsPage";
import { getHealth } from "./api/client";

type ConnectionState =
  | { status: "loading" }
  | { status: "connected"; version: string }
  | { status: "unavailable" };
type Route = "/" | "/results" | "not-found";

function currentRoute(): Route {
  const pathname = window.location.pathname.replace(/\/+$/, "") || "/";
  if (pathname === "/" || pathname === "/results") return pathname;
  return "not-found";
}

function useConnection(): ConnectionState {
  const [connection, setConnection] = useState<ConnectionState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    async function checkBackend() {
      try {
        const health = await getHealth({ signal: controller.signal });
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
  return connection;
}

function AppLink({ children, href, onNavigate, active = false }: {
  children: ReactNode;
  href: string;
  onNavigate: (href: string) => void;
  active?: boolean;
}) {
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (event.currentTarget.target && event.currentTarget.target !== "_self") return;
    event.preventDefault();
    onNavigate(href);
  }
  return <a href={href} onClick={handleClick} aria-current={active ? "page" : undefined}>{children}</a>;
}

export default function App() {
  const [route, setRoute] = useState<Route>(currentRoute);
  const connection = useConnection();

  useEffect(() => {
    const handlePopState = () => setRoute(currentRoute());
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  function navigate(href: string) {
    if (window.location.pathname !== href) window.history.pushState({}, "", href);
    setRoute(currentRoute());
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const connectionText = connection.status === "connected"
    ? `API ${connection.version}`
    : connection.status === "unavailable" ? "API 연결 안 됨" : "API 확인 중";

  return (
    <div className="app-shell">
      <header className="app-header">
        <AppLink href="/" onNavigate={navigate}>
          <span className="brand">Reduce &amp; Compare</span>
          <span className="brand-sub">표 데이터 축소 워크스페이스</span>
        </AppLink>
        <nav aria-label="주요 화면">
          <AppLink href="/" onNavigate={navigate} active={route === "/"}>업로드</AppLink>
          <AppLink href="/results" onNavigate={navigate} active={route === "/results"}>결과</AppLink>
        </nav>
        <p className={`connection connection--${connection.status}`} role="status" aria-live="polite">
          <span className="connection__dot" aria-hidden="true" />{connectionText}
        </p>
      </header>
      <main>
        {route === "/" && <UploadPage onComplete={(jobId) => navigate(`/results?job=${encodeURIComponent(jobId)}`)} />}
        {route === "/results" && <ResultsPage jobId={new URLSearchParams(window.location.search).get("job")} />}
        {route === "not-found" && (
          <section className="page-card not-found" aria-labelledby="not-found-title">
            <span className="eyebrow">404</span>
            <h2 id="not-found-title">요청한 화면을 찾을 수 없습니다</h2>
            <p className="lead">주소를 확인하거나 업로드 화면에서 다시 시작하세요.</p>
            <AppLink href="/" onNavigate={navigate}>업로드 화면으로 이동</AppLink>
          </section>
        )}
      </main>
    </div>
  );
}
