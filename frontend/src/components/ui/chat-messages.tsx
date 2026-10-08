// Adapted from the ChatMessages component supplied by the user on 8 October 2026.
// Presentation only: no example messages, autoplay timers, or simulated responses.
import type {ReactNode} from "react";
import {motion, useReducedMotion} from "framer-motion";
import {Sparkles} from "lucide-react";

export function ChatMessageBubble({sender,children}:{sender:"user"|"assistant";children:ReactNode}) {
  const reduced=useReducedMotion();
  const user=sender==="user";
  return <motion.div
    initial={reduced?false:{opacity:0,y:12,scale:.96,x:user?20:-20}}
    animate={{opacity:1,y:0,scale:1,x:0}}
    transition={{duration:.35,ease:[.22,1,.36,1]}}
    className={`vero-chat-row ${user?"is-user":"is-assistant"}`}
  >
    {!user&&<div className="vero-chat-avatar" aria-hidden="true"><Sparkles size={15}/></div>}
    <div className="vero-chat-bubble">{children}</div>
  </motion.div>;
}

export function ChatTypingIndicator({label}:{label:string}) {
  const reduced=useReducedMotion();
  return <motion.div initial={reduced?false:{opacity:0,scale:.9}} animate={{opacity:1,scale:1}} exit={{opacity:0,scale:.9}} transition={{duration:.2}} className="vero-chat-typing" role="status" aria-label={label}>
    {[0,1,2].map(i=><motion.span key={i} aria-hidden="true" animate={reduced?{}:{opacity:[.4,1,.4],y:[0,-4,0]}} transition={{duration:.8,repeat:Infinity,delay:i*.15,ease:"easeInOut"}}/>)}
    <span className="sr-only">{label}</span>
  </motion.div>;
}
