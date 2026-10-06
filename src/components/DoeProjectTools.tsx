import React, { useState } from "react";
import { Loader2, Pencil, Plus, Trash2, Upload, X } from "lucide-react";
import {
  createProjectUpdate,
  deleteProjectDocument,
  deleteProjectUpdate,
  updateProjectUpdate,
  uploadProjectDocument,
} from "../api";
import { ProjectDocument, ProjectUpdate } from "../types";

const errorMessage = (err: any, fallback: string) => {
  const raw = String(err?.message || "");
  const detail = raw.match(/"detail"\s*:\s*"([^"]+)"/)?.[1];
  return detail || fallback;
};

const formatDateTime = (value?: string) => (value ? new Date(value).toLocaleString() : "N/A");

/** Regional notes a DoE officer posts on a project; they can edit or delete only their own. */
export function DoeRegionalNotesPanel({
  projectId,
  notes,
  currentUserId,
  onChanged,
}: {
  projectId: string;
  notes: ProjectUpdate[];
  currentUserId?: string;
  onChanged: () => Promise<void> | void;
}) {
  const [editingId, setEditingId] = useState<string | "new" | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startNew = () => {
    setEditingId("new");
    setTitle("Regional observation");
    setBody("");
    setError(null);
  };

  const startEdit = (note: ProjectUpdate) => {
    setEditingId(note.id);
    setTitle(note.title || "");
    setBody(note.body);
    setError(null);
  };

  const save = async () => {
    if (!body.trim()) {
      setError("Write the note before saving.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (editingId === "new") {
        await createProjectUpdate({ projectId, title: title.trim(), body: body.trim() });
      } else if (editingId) {
        await updateProjectUpdate(editingId, { title: title.trim(), body: body.trim() });
      }
      setEditingId(null);
      await onChanged();
    } catch (err) {
      setError(errorMessage(err, "Unable to save the note."));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (note: ProjectUpdate) => {
    if (!window.confirm("Delete this note? This cannot be undone.")) return;
    try {
      await deleteProjectUpdate(note.id);
      await onChanged();
    } catch (err) {
      alert(errorMessage(err, "Unable to delete the note."));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h4 className="text-sm font-semibold text-slate-800">Regional Notes</h4>
          <p className="text-xs text-slate-500">
            Observations and updates on this project. You can edit or delete the notes you posted.
          </p>
        </div>
        {editingId === null && (
          <button type="button" onClick={startNew} className="btn-primary inline-flex items-center gap-2 text-xs">
            <Plus size={14} /> Add Note
          </button>
        )}
      </div>

      {editingId !== null && (
        <div className="space-y-3 rounded-2xl border border-emerald-200 bg-emerald-50/40 p-4">
          <input
            className="input-field"
            placeholder="Title"
            value={title}
            maxLength={255}
            onChange={(e) => setTitle(e.target.value)}
          />
          <textarea
            className="input-field min-h-[110px]"
            placeholder="What did you observe or need to record?"
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          {error && <p className="text-xs text-rose-600">{error}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setEditingId(null)} className="btn-secondary text-xs" disabled={saving}>
              Cancel
            </button>
            <button type="button" onClick={() => void save()} className="btn-primary inline-flex items-center gap-2 text-xs" disabled={saving}>
              {saving && <Loader2 size={14} className="animate-spin" />}
              {editingId === "new" ? "Post Note" : "Save Changes"}
            </button>
          </div>
        </div>
      )}

      <div className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white">
        {notes.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-slate-500">No notes on this project yet.</p>
        ) : (
          notes.map((note) => {
            const own = Boolean(currentUserId) && note.author === currentUserId;
            return (
              <div key={note.id} className="flex items-start justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900">{note.title || "Note"}</p>
                  <p className="mt-1 whitespace-pre-line text-sm text-slate-700">{note.body}</p>
                  <p className="mt-1 text-xs text-slate-400">
                    {note.authorUsername || "System"} • {formatDateTime(note.createdAt)}
                  </p>
                </div>
                {own && editingId === null && (
                  <div className="flex shrink-0 gap-1">
                    <button type="button" onClick={() => startEdit(note)} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100" title="Edit">
                      <Pencil size={14} />
                    </button>
                    <button type="button" onClick={() => void remove(note)} className="rounded-lg p-1.5 text-rose-500 hover:bg-rose-50" title="Delete">
                      <Trash2 size={14} />
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

/** Upload form for regional documents (site photos, inspection reports, letters). */
export function DoeDocumentUploader({
  projectId,
  onUploaded,
}: {
  projectId: string;
  onUploaded: (document: ProjectDocument) => void;
}) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setOpen(false);
    setTitle("");
    setFile(null);
    setError(null);
  };

  const upload = async () => {
    if (!file) {
      setError("Choose a file to upload.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const document = await uploadProjectDocument({ projectId, title: title.trim() || `Regional — ${file.name}`, file });
      onUploaded(document);
      reset();
    } catch (err) {
      setError(errorMessage(err, "Unable to upload the document. PDF, JPG and PNG files are accepted."));
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="btn-primary inline-flex items-center gap-2 text-xs">
        <Upload size={14} /> Upload Regional Document
      </button>
    );
  }

  return (
    <div className="w-full space-y-3 rounded-2xl border border-emerald-200 bg-emerald-50/40 p-4 md:max-w-md">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-slate-800">Upload Regional Document</p>
        <button type="button" onClick={reset} className="text-slate-400 hover:text-slate-600" aria-label="Close">
          <X size={16} />
        </button>
      </div>
      <input
        className="input-field"
        placeholder="Title, e.g. Regional — Site inspection report"
        value={title}
        maxLength={255}
        onChange={(e) => setTitle(e.target.value)}
      />
      <input
        type="file"
        accept=".pdf,.jpg,.jpeg,.png"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="block w-full text-sm text-slate-600"
      />
      {error && <p className="text-xs text-rose-600">{error}</p>}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={reset} className="btn-secondary text-xs" disabled={saving}>Cancel</button>
        <button type="button" onClick={() => void upload()} className="btn-primary inline-flex items-center gap-2 text-xs" disabled={saving || !file}>
          {saving && <Loader2 size={14} className="animate-spin" />} Upload
        </button>
      </div>
    </div>
  );
}

export async function confirmAndDeleteProjectDocument(document: ProjectDocument): Promise<boolean> {
  if (!window.confirm(`Delete "${document.title || "this document"}"? This cannot be undone.`)) return false;
  try {
    await deleteProjectDocument(document.id);
    return true;
  } catch (err) {
    alert(errorMessage(err, "Unable to delete the document."));
    return false;
  }
}
