(async () => {
  const api = window.electronAPI;
  const text = "ISSUE3038_TRANSCRIPT Grüße 日本語 🧪";
  await api.saveTranscription(text, text);
  const note = await api.saveNote("ISSUE3038FTS Grüße", "<p>日本語 🧪 database persistence</p>", "personal");
  if (!note.success) throw new Error(JSON.stringify(note));
  const found = await api.searchNotes("ISSUE3038FTS", 50);
  if (!found.some((item) => item.id === note.note.id)) throw new Error("New note missing from FTS");
  const temporary = await api.saveNote("ISSUE3038TEMP", "<p>temporary</p>", "personal");
  if (!temporary.success) throw new Error(JSON.stringify(temporary));
  const updated = await api.updateNote(temporary.note.id, { title: "ISSUE3038UPDATED" });
  if (!updated.success) throw new Error(JSON.stringify(updated));
  if (!(await api.searchNotes("ISSUE3038UPDATED", 50)).some((item) => item.id === temporary.note.id)) {
    throw new Error("Updated note missing from FTS");
  }
  const removed = await api.deleteNote(temporary.note.id);
  if (!removed.success) throw new Error(JSON.stringify(removed));
  if ((await api.searchNotes("ISSUE3038UPDATED", 50)).length) throw new Error("Deleted note still in FTS");
  const rows = await api.getTranscriptions(50);
  if (!rows.some((item) => item.text === text)) throw new Error("Saved transcript missing");
  return { transcript: text, note: note.note.id, fts: found.length, updateAndDeletePassed: true };
})()
