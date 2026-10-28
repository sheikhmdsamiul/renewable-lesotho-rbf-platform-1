import React, { useCallback, useEffect, useState } from "react";
import {
  answerTenderClarification,
  askTenderClarification,
  fetchTenderAddenda,
  fetchTenderBidOpening,
  fetchTenderClarifications,
  issueTenderAddendum,
  recordTenderBidOpening,
  TenderAddendum,
  TenderBidOpeningRecord,
  TenderClarification,
} from "../api";
import { Tender, TenderStatus } from "../types";

const formatWhen = (iso?: string | null) => (iso ? new Date(iso).toLocaleString() : "—");

/**
 * Clarification Q&A and addenda for one tender. Vendors ask questions (until the
 * clarification deadline) and read every published answer and addendum; the RBF
 * answers questions — each answer goes to every bidder, never naming the asker — and
 * issues numbered addenda while the tender is published.
 */
export function TenderClarifications({ tender, mode }: { tender: Tender; mode: "vendor" | "staff" }) {
  const [clarifications, setClarifications] = useState<TenderClarification[]>([]);
  const [addenda, setAddenda] = useState<TenderAddendum[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [addendumTitle, setAddendumTitle] = useState("");
  const [addendumDescription, setAddendumDescription] = useState("");
  const [addendumFile, setAddendumFile] = useState<File | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const [qs, ads] = await Promise.all([fetchTenderClarifications(tender.id), fetchTenderAddenda(tender.id)]);
      setClarifications(qs);
      setAddenda(ads);
    } catch (err: any) {
      setLoadError(err?.message || "Could not load clarifications.");
    }
  }, [tender.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setActionError(null);
    try {
      await action();
      await load();
    } catch (err: any) {
      setActionError(err?.message || "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  const isPublished = tender.status === TenderStatus.PUBLISHED;
  const questionDeadline = tender.clarificationDeadline || tender.technicalDeadline || tender.deadline;
  const questionsOpen = isPublished && (!questionDeadline || new Date(questionDeadline).getTime() > Date.now());

  return (
    <div className="card p-6 space-y-6">
      <div>
        <h3 className="text-base font-bold text-slate-900">Clarifications &amp; Addenda</h3>
        <p className="text-xs text-slate-500">
          Answers are shared with every bidder without naming who asked.
          {questionDeadline ? ` Questions close ${formatWhen(questionDeadline)}.` : ""}
        </p>
      </div>
      {loadError && <p className="text-sm text-red-600">{loadError}</p>}
      {actionError && <p className="text-sm text-red-600">{actionError}</p>}

      <div className="space-y-3">
        <p className="text-xs font-bold uppercase tracking-widest text-slate-400">Addenda</p>
        {addenda.length === 0 && <p className="text-sm text-slate-500">No addenda issued.</p>}
        {addenda.map((a) => (
          <div key={a.id} className="rounded-xl border border-slate-200 p-3">
            <p className="text-sm font-semibold text-slate-900">Addendum {a.number}: {a.title}</p>
            <p className="text-xs text-slate-500 mb-1">Issued {formatWhen(a.issued_at)}</p>
            <p className="text-sm text-slate-700 whitespace-pre-wrap">{a.description}</p>
            {a.document && (
              <a href={a.document} target="_blank" rel="noreferrer" className="text-xs font-semibold text-emerald-700">
                Download document
              </a>
            )}
          </div>
        ))}
        {mode === "staff" && isPublished && (
          <div className="rounded-xl border border-dashed border-slate-300 p-3 space-y-2">
            <input className="input-field" placeholder="Addendum title" value={addendumTitle} onChange={(e) => setAddendumTitle(e.target.value)} />
            <textarea className="input-field" rows={3} placeholder="What does this addendum change?" value={addendumDescription} onChange={(e) => setAddendumDescription(e.target.value)} />
            <input type="file" accept=".pdf,.doc,.docx,.xls,.xlsx" onChange={(e) => setAddendumFile(e.target.files?.[0] ?? null)} />
            <div className="flex justify-end">
              <button
                className="btn-primary text-sm disabled:opacity-40"
                disabled={busy || !addendumTitle.trim() || !addendumDescription.trim()}
                onClick={() =>
                  run(async () => {
                    if (!window.confirm("Issue this addendum? Every vendor following the tender is notified and it cannot be edited.")) return;
                    await issueTenderAddendum(tender.id, { title: addendumTitle.trim(), description: addendumDescription.trim(), document: addendumFile });
                    setAddendumTitle("");
                    setAddendumDescription("");
                    setAddendumFile(null);
                  })
                }
              >
                Issue Addendum
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="space-y-3">
        <p className="text-xs font-bold uppercase tracking-widest text-slate-400">Questions</p>
        {clarifications.length === 0 && <p className="text-sm text-slate-500">No questions yet.</p>}
        {clarifications.map((c) => (
          <div key={c.id} className="rounded-xl border border-slate-200 p-3 space-y-1">
            <p className="text-sm font-semibold text-slate-900">Q: {c.question}</p>
            <p className="text-xs text-slate-500">
              Asked {formatWhen(c.asked_at)}{c.asked_by_me ? " · your question" : ""}
            </p>
            {c.answered_at ? (
              <p className="text-sm text-slate-700 whitespace-pre-wrap">A: {c.answer}</p>
            ) : mode === "staff" ? (
              <div className="space-y-2 pt-1">
                <textarea
                  className="input-field"
                  rows={2}
                  placeholder="Answer (published to every bidder)"
                  value={answers[c.id] || ""}
                  onChange={(e) => setAnswers((prev) => ({ ...prev, [c.id]: e.target.value }))}
                />
                <div className="flex justify-end">
                  <button
                    className="btn-secondary text-sm disabled:opacity-40"
                    disabled={busy || !(answers[c.id] || "").trim()}
                    onClick={() => run(() => answerTenderClarification(tender.id, c.id, (answers[c.id] || "").trim()))}
                  >
                    Publish Answer
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-xs text-amber-700">Awaiting an answer from the RBF.</p>
            )}
          </div>
        ))}
        {mode === "vendor" && (questionsOpen ? (
          <div className="space-y-2">
            <textarea className="input-field" rows={3} placeholder="Ask a question about this tender" value={question} onChange={(e) => setQuestion(e.target.value)} />
            <div className="flex justify-end">
              <button
                className="btn-primary text-sm disabled:opacity-40"
                disabled={busy || !question.trim()}
                onClick={() => run(async () => {
                  await askTenderClarification(tender.id, question.trim());
                  setQuestion("");
                })}
              >
                Ask Question
              </button>
            </div>
          </div>
        ) : (
          <p className="text-xs text-slate-500">The clarification period for this tender has closed.</p>
        ))}
      </div>
    </div>
  );
}

/**
 * The formal bid-opening record (RBF side). Once submissions close, the RBF opens the
 * bids once; the record freezes which submissions were received. Prices are never shown.
 */
export function TenderBidOpeningPanel({ tender }: { tender: Tender }) {
  const [record, setRecord] = useState<TenderBidOpeningRecord | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attendees, setAttendees] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchTenderBidOpening(tender.id)
      .then((r) => { if (!cancelled) setRecord(r); })
      .catch((err: any) => { if (!cancelled) setError(err?.message || "Could not load the bid-opening record."); })
      .finally(() => { if (!cancelled) setLoaded(true); });
    return () => { cancelled = true; };
  }, [tender.id]);

  const canOpen = !record && (tender.status === TenderStatus.CLOSED || tender.status === TenderStatus.EVALUATION);
  if (tender.isEoiInviteOnly || !loaded || (!record && !canOpen && !error)) return null;

  return (
    <div className="card p-6 space-y-3">
      <h3 className="text-base font-bold text-slate-900">Bid Opening</h3>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {record ? (
        <>
          <p className="text-xs text-slate-500">
            Opened {formatWhen(record.opened_at)} by {record.opened_by}
            {record.attendees ? ` · Attendees: ${record.attendees}` : ""}
          </p>
          {record.notes && <p className="text-sm text-slate-700 whitespace-pre-wrap">{record.notes}</p>}
          <p className="text-sm font-semibold text-slate-900">{record.submissions.length} submission(s) received</p>
          <ul className="space-y-1">
            {record.submissions.map((s) => (
              <li key={s.bid_id} className="text-sm text-slate-700">
                {s.vendor_name} — {s.stage} v{s.version_number}, submitted {formatWhen(s.submitted_at)}
              </li>
            ))}
          </ul>
        </>
      ) : canOpen ? (
        <>
          <p className="text-sm text-slate-600">
            Submissions have closed. Record the bid opening to freeze which submissions were received. This is done once and cannot be changed.
          </p>
          <input className="input-field" placeholder="Attendees (e.g. RMT members, observers)" value={attendees} onChange={(e) => setAttendees(e.target.value)} />
          <textarea className="input-field" rows={2} placeholder="Notes (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} />
          <div className="flex justify-end">
            <button
              className="btn-primary text-sm disabled:opacity-40"
              disabled={busy}
              onClick={async () => {
                if (!window.confirm("Record the bid opening now? This cannot be undone.")) return;
                setBusy(true);
                setError(null);
                try {
                  setRecord(await recordTenderBidOpening(tender.id, { attendees: attendees.trim(), notes: notes.trim() }));
                } catch (err: any) {
                  setError(err?.message || "Could not record the bid opening.");
                } finally {
                  setBusy(false);
                }
              }}
            >
              Record Bid Opening
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}
