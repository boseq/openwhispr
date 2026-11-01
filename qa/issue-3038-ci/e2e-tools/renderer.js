(() => {
  const text = document.body?.innerText || "";
  return {
    ready: document.readyState === "complete" && !!window.electronAPI &&
      text.includes("Welcome to OpenWhispr") && !!document.querySelector("button"),
    title: document.title,
    text: text.slice(0, 1500),
    size: { width: innerWidth, height: innerHeight },
  };
})()
