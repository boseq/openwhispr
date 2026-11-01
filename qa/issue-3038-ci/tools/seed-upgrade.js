(async () => {
  const text = "ISSUE3038_UPGRADE Grüße 日本語 🧪";
  const saved = await window.electronAPI.saveTranscription(text, text);
  const rows = await window.electronAPI.getTranscriptions(50);
  return { saved, rows };
})()
