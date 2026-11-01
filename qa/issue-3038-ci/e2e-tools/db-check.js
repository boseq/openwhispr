(async () => {
  const api = window.electronAPI;
  const rows = await api.getTranscriptions(50);
  if (!rows.some((item) => item.text === "ISSUE3038_TRANSCRIPT Grüße 日本語 🧪")) {
    throw new Error("Transcript did not survive restart/upgrade");
  }
  const notes = await api.searchNotes("ISSUE3038FTS", 50);
  if (!notes.length) throw new Error("FTS note did not survive restart/upgrade");
  const note = await api.getNote(notes[0].id);
  if (!note.content.includes("日本語 🧪")) throw new Error("Unicode note content lost");
  return { persistencePassed: true, transcriptCount: rows.length, ftsCount: notes.length };
})()
