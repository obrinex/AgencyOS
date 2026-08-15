import { useEffect, useRef, useState } from "react";
import { Upload, FolderOpen, Download, File as FileIcon, Loader2 } from "lucide-react";
import api, { API } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { format } from "date-fns";

/** Files, both directions.
 *
 *  The whole card is the download, rather than a button inside a card that is
 *  itself not clickable — on a phone that button was a 32px target inside a
 *  120px card that did nothing.
 */

const EXT = (name = "") => (name.split(".").pop() || "").slice(0, 4).toUpperCase();

function hueOf(text = "") {
  let h = 0;
  for (let i = 0; i < text.length; i += 1) h = (h * 31 + text.charCodeAt(i)) % 360;
  return h;
}

export default function PortalFiles() {
  const [files, setFiles] = useState(null);
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/portal/files");
      setFiles(data);
    } catch {
      setFiles([]);
    }
  };

  useEffect(() => { load(); }, []);

  const upload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    try {
      await api.post("/files/upload?related_type=client", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("File uploaded.");
      load();
    } catch {
      toast.error("Upload failed.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const download = (id) => window.open(`${API}/files/${id}/download`, "_blank");

  if (!files) {
    return <div className="p-4 sm:p-6"><Skeleton className="h-64 w-full rounded-2xl bg-surface-1" /></div>;
  }

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-6" data-testid="portal-files-page">
      <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight">Files</h1>
          <p className="mt-1 text-sm text-graphite">
            {files.length === 0 ? "Nothing yet." : `${files.length} in total`}
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          onChange={upload}
          className="hidden"
          data-testid="portal-file-upload-input"
        />
        <button
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          data-testid="portal-open-upload-btn"
          className="flex items-center gap-1.5 rounded-xl bg-primary px-3.5 py-2 text-sm font-medium text-background disabled:opacity-50"
        >
          {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
          {uploading ? "Uploading…" : "Upload file"}
        </button>
      </header>

      {files.length === 0 ? (
        <div className="obx-glass rounded-2xl px-6 py-14 text-center" data-testid="portal-files-empty">
          <div className="obx-holo obx-glass relative mx-auto flex h-14 w-14 items-center justify-center overflow-hidden rounded-2xl">
            <FolderOpen className="relative z-10 h-5 w-5 text-primary" />
          </div>
          <p className="mt-4 text-sm">No files yet.</p>
          <p className="mx-auto mt-1 max-w-xs text-xs text-graphite">
            Upload anything your team needs, or find deliverables shared with you here.
          </p>
        </div>
      ) : (
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {files.map((f, i) => {
            const hue = hueOf(f.original_name || "");
            return (
              <button
                key={f.id}
                onClick={() => download(f.id)}
                data-testid={`portal-download-file-${f.id}`}
                style={{ animationDelay: `${i * 35}ms` }}
                className="obx-glass obx-lift obx-sheen obx-reveal group flex items-center gap-3 rounded-2xl p-3.5 text-left"
              >
                <div
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl font-mono text-[9px] font-bold"
                  style={{
                    background: `hsl(${hue} 60% 55% / 0.14)`,
                    color: `hsl(${hue} 70% 78%)`,
                    boxShadow: `inset 0 0 0 1px hsl(${hue} 60% 60% / 0.28)`,
                  }}
                >
                  {EXT(f.original_name) || <FileIcon className="h-4 w-4" />}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm" data-testid={`portal-file-card-${f.id}`}>
                    {f.original_name}
                  </p>
                  <p className="mt-0.5 font-mono text-[10px] text-carbon">
                    {f.created_at ? format(new Date(f.created_at), "d MMM yyyy") : ""}
                  </p>
                </div>
                <Download className="h-4 w-4 shrink-0 text-carbon transition-colors group-hover:text-primary" />
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
