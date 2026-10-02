import { useRef, useState, type ChangeEvent, type DragEvent, type InputHTMLAttributes } from "react";

type SelectedFile = { file: File; path: string };
type DirectoryInputProps = InputHTMLAttributes<HTMLInputElement> & {
  directory?: string;
  webkitdirectory?: string;
};
const SUPPORTED_EXTENSIONS = new Set([".csv", ".tsv", ".txt"]);
const directoryAttributes: DirectoryInputProps = { directory: "", webkitdirectory: "" };

function isSupported(path: string) {
  const dot = path.lastIndexOf(".");
  return dot >= 0 && SUPPORTED_EXTENSIONS.has(path.slice(dot).toLowerCase());
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} ${units[unit]}`;
}

function readEntries(reader: FileSystemDirectoryReader) {
  return new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject));
}

function entryFile(entry: FileSystemFileEntry) {
  return new Promise<File>((resolve, reject) => entry.file(resolve, reject));
}

async function walkEntry(entry: FileSystemEntry): Promise<SelectedFile[]> {
  if (entry.isFile) {
    const file = await entryFile(entry as FileSystemFileEntry);
    return [{ file, path: entry.fullPath.replace(/^\/+/, "") || file.name }];
  }
  if (!entry.isDirectory) return [];
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  const found: SelectedFile[] = [];
  for (;;) {
    const entries = await readEntries(reader);
    if (!entries.length) return found;
    const nested = await Promise.all(entries.map(walkEntry));
    found.push(...nested.flat());
  }
}

async function droppedFiles(dataTransfer: DataTransfer): Promise<SelectedFile[]> {
  const entries = Array.from(dataTransfer.items)
    .map((item) => item.webkitGetAsEntry())
    .filter((entry): entry is FileSystemEntry => Boolean(entry));
  if (entries.length) return (await Promise.all(entries.map(walkEntry))).flat();
  return Array.from(dataTransfer.files).map((file) => ({ file, path: file.webkitRelativePath || file.name }));
}

function SelectionPreview({ files, excluded, onClear }: {
  files: SelectedFile[];
  excluded: number;
  onClear: () => void;
}) {
  const totalSize = files.reduce((sum, item) => sum + item.file.size, 0);
  return (
    <section className="selection" aria-labelledby="selection-title" aria-live="polite">
      <div className="selection__header">
        <div>
          <h3 id="selection-title">선택한 표 파일</h3>
          <p>
            {files.length}개 · {formatBytes(totalSize)}
            {excluded > 0 && <span> · 지원하지 않는 파일 {excluded}개 제외</span>}
          </p>
        </div>
        <button type="button" className="text-button" onClick={onClear}>선택 지우기</button>
      </div>
      {files.length > 0 ? (
        <ul className="file-list">
          {files.map((item, index) => (
            <li key={`${item.path}-${index}`}>
              <span title={item.path}>{item.path}</span>
              <data value={item.file.size}>{formatBytes(item.file.size)}</data>
            </li>
          ))}
        </ul>
      ) : (
        <p className="selection__empty">지원하는 표 파일이 없습니다. CSV, TSV 또는 TXT 파일이 있는 폴더를 선택하세요.</p>
      )}
    </section>
  );
}

export default function FolderPicker() {
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const [files, setFiles] = useState<SelectedFile[]>([]);
  const [excluded, setExcluded] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [hasSelection, setHasSelection] = useState(false);

  function applySelection(selection: SelectedFile[]) {
    const supported = selection.filter((item) => isSupported(item.path));
    setFiles(supported.sort((left, right) => left.path.localeCompare(right.path, "ko")));
    setExcluded(selection.length - supported.length);
    setHasSelection(true);
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const selection = Array.from(event.currentTarget.files ?? []).map((file) => ({
      file,
      path: file.webkitRelativePath || file.name,
    }));
    applySelection(selection);
    event.currentTarget.value = "";
  }

  async function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragDepth.current = 0;
    setIsDragging(false);
    try {
      applySelection(await droppedFiles(event.dataTransfer));
    } catch {
      applySelection([]);
    }
  }

  function clearSelection() {
    setFiles([]);
    setExcluded(0);
    setHasSelection(false);
  }

  return (
    <div className="folder-picker">
      <div
        className={`drop-zone${isDragging ? " drop-zone--active" : ""}`}
        onDragEnter={(event) => { event.preventDefault(); dragDepth.current += 1; setIsDragging(true); }}
        onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; }}
        onDragLeave={(event) => {
          event.preventDefault();
          dragDepth.current = Math.max(0, dragDepth.current - 1);
          if (!dragDepth.current) setIsDragging(false);
        }}
        onDrop={(event) => { void handleDrop(event); }}
      >
        <input
          {...directoryAttributes}
          ref={inputRef}
          className="sr-only"
          type="file"
          accept=".csv,.tsv,.txt"
          multiple
          onChange={handleChange}
          aria-label="데이터 폴더 선택"
        />
        <span className="drop-zone__icon" aria-hidden="true">{isDragging ? "↓" : "+"}</span>
        <strong>{isDragging ? "여기에 폴더를 놓으세요" : "폴더를 끌어다 놓으세요"}</strong>
        <span>또는 이 컴퓨터에서 폴더를 선택하세요</span>
        <button type="button" className="primary-button" onClick={() => inputRef.current?.click()}>
          {hasSelection ? "다른 폴더 선택" : "폴더 선택"}
        </button>
      </div>

      {hasSelection && <SelectionPreview files={files} excluded={excluded} onClear={clearSelection} />}
    </div>
  );
}
