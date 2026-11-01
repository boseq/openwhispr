(async () => ({ rows: await window.electronAPI.getTranscriptions(50) }))()
