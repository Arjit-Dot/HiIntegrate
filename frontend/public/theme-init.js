// Sets the dark class before the page paints, so there is no flash. It is a separate file, not an inline script,
// because the Content-Security-Policy (nginx.conf) does not allow inline scripts (D-17 S-2).
try {
  var t = localStorage.getItem('theme')
  if (t === 'dark' || (!t && matchMedia('(prefers-color-scheme: dark)').matches)) document.documentElement.classList.add('dark')
} catch (e) {}
