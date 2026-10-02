import { useEffect, useRef, useState, type FormEvent } from "react";

import FolderPicker from "./FolderPicker";
import { ApiError, createJob, type JobCreated, type UploadItem } from "./api/client";

type UploadState =
  | { status: "idle" }
  | { status: "uploading" }
  | { status: "success"; job: JobCreated }
  | { status: "error"; message: string };

function uploadMessage(error: unknown) {
  if (error instanceof ApiError) return error.message;
  return "업로드 중 예상하지 못한 오류가 발생했습니다";
}

export default function UploadPage() {
  const [files, setFiles] = useState<UploadItem[]>([]);
  const [upload, setUpload] = useState<UploadState>({ status: "idle" });
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => () => activeRequest.current?.abort(), []);

  function handleSelectionChange(selection: UploadItem[]) {
    setFiles(selection);
    setUpload({ status: "idle" });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!files.length || activeRequest.current) return;
    const controller = new AbortController();
    activeRequest.current = controller;
    setUpload({ status: "uploading" });
    try {
      const job = await createJob(files, { signal: controller.signal });
      if (activeRequest.current === controller) setUpload({ status: "success", job });
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        setUpload({ status: "error", message: uploadMessage(error) });
      }
    } finally {
      if (activeRequest.current === controller) activeRequest.current = null;
    }
  }

  const busy = upload.status === "uploading";
  const finished = upload.status === "success";

  return (
    <section className="page-card" aria-labelledby="upload-title">
      <span className="eyebrow">1단계 · 데이터 준비</span>
      <h2 id="upload-title">분석할 데이터 폴더를 선택하세요</h2>
      <p className="lead">CSV, TSV, 구분자 텍스트 파일을 전송 전에 확인할 수 있습니다.</p>
      <form onSubmit={(event) => { void handleSubmit(event); }}>
        <FolderPicker disabled={busy} onSelectionChange={handleSelectionChange} />
        <div className="upload-actions">
          <button
            type="submit"
            className="upload-button"
            disabled={!files.length || busy || finished}
          >
            {busy ? "업로드 중…" : finished ? "업로드 완료" : `${files.length}개 파일 업로드`}
          </button>
          {!files.length && <span>지원하는 파일을 먼저 선택하세요.</span>}
        </div>
      </form>

      {busy && (
        <div className="upload-status upload-status--busy" role="status" aria-live="polite">
          <strong>파일을 안전하게 전송하고 있습니다</strong>
          <span>창을 닫거나 다른 화면으로 이동하지 마세요.</span>
          <progress aria-label="파일 업로드 진행 중" />
        </div>
      )}
      {upload.status === "error" && (
        <div className="upload-status upload-status--error" role="alert">
          <strong>업로드하지 못했습니다</strong>
          <span>{upload.message}</span>
          <span>선택한 파일은 유지됩니다. 다시 업로드할 수 있습니다.</span>
        </div>
      )}
      {upload.status === "success" && (
        <div className="upload-status upload-status--success" role="status" aria-live="polite">
          <strong>업로드가 완료되었습니다</strong>
          <span>서버에서 {upload.job.files.length}개 파일을 확인했습니다.</span>
          <span>작업 번호</span>
          <code>{upload.job.job_id}</code>
        </div>
      )}
    </section>
  );
}
