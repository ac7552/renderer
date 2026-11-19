// The page's script: Stimulus, and the two controllers the page has (the fitting room, and the light switch).
import { Application } from "@hotwired/stimulus"
import FittingRoomController from "controllers/fitting_room_controller"
import LightController from "controllers/light_controller"

const application = Application.start()
application.register("fitting-room", FittingRoomController)
application.register("light", LightController)
