import { useEffect, useRef, useState } from "react";
import { Upload, FolderOpen, Download, Trash2, FileIcon } from "lucide-react";
import api, { API } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import EmptyState from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { format } from "date-fns";

export default function Files() {
  const [files, setFiles] = useState(null);
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);

  const load = async () => {
    const { data } = await api.get("/files?related_type=general");
    setFiles(data);
  };

  useEffect(() => { load(); }, []);

  const upload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);
    try {
      await api.post("/files/upload?related_type=general", formData, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("File uploaded");
      load();
    } catch (err) {
      toast.error("Upload failed");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const download = (id) => {
    window.open(`${API}/files/${id}/download`, "_blank");
  };

  const remove = async (id) => {
    await api.delete(`/files/${id}`);
    load();
  };

  if (!files) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  return (
    <div className="p-6" data-testid="files-page">
      <PageHeader
        title="Files"
        description={`${files.length} files`}
        actions={
          <>
            <input ref={inputRef} type="file" onChange={upload} className="hidden" data-testid="file-upload-input" />
            <Button size="sm" className="gap-1.5" onClick={() => inputRef.current?.click()} disabled={uploading} data-testid="open-file-upload-btn">
              <Upload className="h-3.5 w-3.5" /> {uploading ? "Uploading..." : "Upload File"}
            </Button>
          </>
        }
      />
      {files.length === 0 ? (
        <EmptyState icon={FolderOpen} title="No files yet" description="Upload files to share and organize agency documents." testId="files-empty-state" />
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {files.map((f) => (
            <Card key={f.id} data-testid={`file-card-${f.id}`} className="p-4 bg-surface-1 border-white/10">
              <div className="flex items-center gap-2">
                <FileIcon className="h-4 w-4 text-graphite shrink-0" />
                <p className="text-sm truncate flex-1">{f.original_name}</p>
              </div>
              <p className="text-[10px] font-mono text-carbon mt-2">{(f.size / 1024).toFixed(1)} KB · {format(new Date(f.created_at), "MMM d, yyyy")}</p>
              <div className="mt-3 flex gap-2">
                <Button size="sm" variant="outline" className="border-white/10 flex-1 gap-1.5" onClick={() => download(f.id)} data-testid={`download-file-${f.id}`}><Download className="h-3.5 w-3.5" /> Download</Button>
                <Button size="icon" variant="outline" className="border-white/10" onClick={() => remove(f.id)} data-testid={`delete-file-${f.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
