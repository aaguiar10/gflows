// Retrieve user preference and theme links from localStorage
let themeToggle = localStorage.getItem('_dash_persistence.switch.value.true')
let themeStore = localStorage.getItem('theme-store')

if (themeToggle && themeStore) {
  themeToggle = JSON.parse(themeToggle)[0]
  themeStore = JSON.parse(themeStore)
  let themeLink = themeToggle ? themeStore[1] : themeStore[0]
  let stylesheets = document.querySelectorAll(
    'link[rel=stylesheet][href^="https://cdn.jsdelivr"]'
  )
  // Update main theme
  stylesheets[1].href = themeLink
  // Update buffer after a short delay
  setTimeout(() => {
    stylesheets[0].href = themeLink
  }, 100)
}
