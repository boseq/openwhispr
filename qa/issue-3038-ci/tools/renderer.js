({
  ready: document.readyState,
  title: document.title,
  text: document.body.innerText.slice(0, 1500),
  size: { width: innerWidth, height: innerHeight },
})
