// The site's light. The room on the front page is lit by the reader's clock (daylight from 7 to 6, the cabinet's
// own lamps at night) unless they hold it to day or night with a light switch (light_controller.js), and every
// other page is the colour of that room's wall in the same light: <html class="is-night"> says which
// (outlet.css). The choice is kept in this browser. The page's head sets the class before anything is drawn
// (layouts/application.html.erb), with the same sum as nightAt.
const KEY = "fitroom:light"
export const MODES = ["auto", "day", "night"]

// Night, for a mode and an hour of the reader's day.
export function nightAt(mode, hour) { return mode === "night" || (mode !== "day" && (hour < 7 || hour >= 18)) }

let chosen = null, clock = null

export function lightMode() {
  if (chosen) return chosen
  try { const held = window.localStorage.getItem(KEY); return MODES.includes(held) ? held : "auto" } catch { return "auto" }
}

export function isNight() { return nightAt(lightMode(), new Date().getHours()) }

function tell() { window.dispatchEvent(new CustomEvent("fitroom:light", { detail: { mode: lightMode(), night: isNight() } })) }

// Put the page in its light. Anything that draws by it hears "fitroom:light" on the window when it changes.
export function showLight() {
  const root = document.documentElement, night = isNight()
  if (root.classList.contains("is-night") === night) return night
  root.classList.toggle("is-night", night)
  tell()
  return night
}

// Hold the light to day or night, or give it back to the clock ("auto").
export function holdLight(mode) {
  chosen = MODES.includes(mode) ? mode : "auto"
  try { chosen === "auto" ? window.localStorage.removeItem(KEY) : window.localStorage.setItem(KEY, chosen) } catch { /* a private window: the choice lasts the visit */ }
  document.documentElement.classList.toggle("is-night", isNight())
  tell()
}

// Keep the light right as the clock passes 7 and 6. Safe to call from every switch and room on the page.
export function watchLight() {
  clock ||= setInterval(showLight, 60000)
  return showLight()
}
