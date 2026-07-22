// Type declarations for three.js example modules.
// Next.js 15 + bundler moduleResolution can't always resolve
// three's subpath exports through @types/three's exports map.
// This file provides explicit declarations.
declare module "three/examples/jsm/controls/OrbitControls" {
  import { OrbitControls } from "three";
  export { OrbitControls };
  export default OrbitControls;
}

declare module "three/examples/jsm/postprocessing/EffectComposer" {
  import { EffectComposer } from "three";
  export { EffectComposer };
  export default EffectComposer;
}

declare module "three/examples/jsm/postprocessing/RenderPass" {
  import { RenderPass } from "three";
  export { RenderPass };
  export default RenderPass;
}

declare module "three/examples/jsm/postprocessing/UnrealBloomPass" {
  import { UnrealBloomPass } from "three";
  export { UnrealBloomPass };
  export default UnrealBloomPass;
}
