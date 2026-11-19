import { Controller } from "@hotwired/stimulus"
import { lightMode, holdLight, watchLight } from "lib/light"

// A light switch: Your clock, Day, Night (shared/_light). One in the room's corner, one in the masthead's menu on every
// page. Pressing one lights the room and colours every page the same way (lib/light.js), and every switch on
// the page shows what's held. Hidden until this runs: without scripts there's only daylight.
export default class extends Controller {
  static targets = ["mode"]

  connect() {
    this.heard = () => this.show()
    window.addEventListener("fitroom:light", this.heard)
    watchLight()
    this.show()
    this.element.hidden = false
  }

  disconnect() { window.removeEventListener("fitroom:light", this.heard) }

  hold({ params: { mode } }) { holdLight(mode) }

  show() {
    const held = lightMode()
    for (const button of this.modeTargets) button.setAttribute("aria-pressed", String(button.dataset.lightModeParam === held))
  }
}
