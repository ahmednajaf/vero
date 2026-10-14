import {motion, useReducedMotion} from 'framer-motion';

// Adapted from the user's animated pricing card: orbital and sliding geometry.
export function PackageArt({variant}:{variant:'company'|'sector'}) {
  const reduced=useReducedMotion();
  const transition={duration:reduced?0:.8,ease:'easeInOut' as const};
  return <motion.svg className="package-art" aria-hidden="true" viewBox="0 0 320 384" fill="none" variants={reduced?{}:{hover:{scale:1.08}}} transition={transition}>
    {variant==='company'?<><motion.circle cx="160.5" cy="114.5" r="101.5" variants={reduced?{}:{hover:{scaleY:.55,y:-20}}} transition={transition}/><motion.ellipse cx="160.5" cy="265.5" rx="101.5" ry="43.5" variants={reduced?{}:{hover:{scaleY:2.1,y:-20}}} transition={transition}/></>:<><motion.rect x="14" y="12" width="153" height="153" rx="25" variants={reduced?{}:{hover:{y:180,rotate:90,scaleX:1.2}}} transition={transition}/><motion.rect x="155" y="219" width="153" height="153" rx="25" variants={reduced?{}:{hover:{y:-180,rotate:90,scaleX:1.2}}} transition={transition}/></>}
  </motion.svg>;
}
