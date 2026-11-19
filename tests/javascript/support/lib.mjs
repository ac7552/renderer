// Lets Node load the page's modules as the browser does: "lib/..." (the importmap's name) is
// app/javascript/lib/....js. Import this, then load those modules with a dynamic import().
import { register } from "node:module"

const root = new URL("../../../renderer/static/js/", import.meta.url).href
register(`data:text/javascript,${encodeURIComponent(`
  export async function resolve(specifier, context, next) {
    if (specifier.startsWith("lib/")) return next(${JSON.stringify(root)} + specifier + ".js", context)
    if (specifier === "three") return next(${JSON.stringify(new URL("../../../renderer/static/js/vendor/three.js", import.meta.url).href)}, context)
    if (specifier === "three-gpu-pathtracer") return next(${JSON.stringify(new URL("../../../renderer/static/js/vendor/three-gpu-pathtracer.js", import.meta.url).href)}, context)
    if (specifier === "three/examples/jsm/postprocessing/Pass.js") return next(${JSON.stringify(new URL("../../../renderer/static/js/vendor/three-addons/Pass.js", import.meta.url).href)}, context)
    if (specifier.startsWith("three/addons/")) return next(${JSON.stringify(new URL("../../../renderer/static/js/vendor/three-addons/", import.meta.url).href)} + specifier.split("/").pop(), context)
    if (specifier === "n8ao" || specifier === "postprocessing") return next(${JSON.stringify(new URL("../../../renderer/static/js/vendor/", import.meta.url).href)} + (specifier === "n8ao" ? "n8ao.js" : "postprocessing-shim.js"), context)
    return next(specifier, context)
  }`)}`)
