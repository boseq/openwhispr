(async () => {
  const deadline = Date.now() + 30000;
  while (!document.body?.innerText.trim() || !window.electronAPI) {
    if (Date.now() > deadline) throw new Error("Renderer did not become ready");
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  return {
  ready: document.readyState,
  title: document.title,
  text: document.body.innerText.slice(0, 1500),
  size: { width: innerWidth, height: innerHeight },
  };
})()
