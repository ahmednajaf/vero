// Silk, adapted from the user's 21st.dev Shader Builder source.
// Only the active Silk field and its supplied palette/finish are needed here.
import { useEffect, useRef } from "react";
const VERT = `attribute vec2 a_position; void main(){gl_Position=vec4(a_position,0.,1.);}`;
const FRAG = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform vec2 u_resolution;
uniform float u_time;
uniform vec3 u_colors[4];
float grainHash(vec2 p){vec3 p3=fract(vec3(p.xyx)*.1031);p3+=dot(p3,p3.yzx+33.33);return fract((p3.x+p3.y)*p3.z);}
vec3 palette(float x){float f=clamp(x,0.,1.)*3.;vec3 col=u_colors[0];for(int i=0;i<3;i++){col=mix(col,u_colors[i+1],smoothstep(0.,1.,clamp(f-float(i),0.,1.)));}return col;}
void main(){
 vec2 p=(gl_FragCoord.xy-.5*u_resolution)/min(u_resolution.x,u_resolution.y);
 vec2 q=p*1.5*1.6;float amp=.25+.55*.85;
 for(float i=1.;i<5.;i+=1.){q.x+=amp/i*cos(i*2.4*q.y+u_time*.8+1.);q.y+=amp/i*cos(i*1.7*q.x+u_time*.6);}
 vec3 col=palette(.5+.5*sin(q.x+q.y));col=(col-.5)*1.005+.5;
 col+=(grainHash(gl_FragCoord.xy+vec2(17.,31.))-.5)*.042;
 gl_FragColor=vec4(clamp(col,0.,1.),1.);
}`;
export function ShaderBackground({className}: {className?: string}) {
 const ref=useRef<HTMLCanvasElement>(null);
 useEffect(()=>{
  const canvas=ref.current;if(!canvas || typeof window.WebGLRenderingContext==='undefined')return;
  const gl=canvas.getContext('webgl',{antialias:false,alpha:false});if(!gl)return;
  const shaders:WebGLShader[]=[];
  function compile(type:number,source:string){const shader=gl!.createShader(type);if(!shader)return null;gl!.shaderSource(shader,source);gl!.compileShader(shader);shaders.push(shader);return gl!.getShaderParameter(shader,gl!.COMPILE_STATUS)?shader:null;}
  const vertex=compile(gl.VERTEX_SHADER,VERT),fragment=compile(gl.FRAGMENT_SHADER,FRAG),program=gl.createProgram();
  if(!vertex||!fragment||!program){shaders.forEach(s=>gl.deleteShader(s));if(program)gl.deleteProgram(program);return;}
  gl.attachShader(program,vertex);gl.attachShader(program,fragment);gl.linkProgram(program);shaders.forEach(s=>gl.deleteShader(s));
  if(!gl.getProgramParameter(program,gl.LINK_STATUS)){gl.deleteProgram(program);return;}
  gl.useProgram(program);const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,3,-1,-1,3]),gl.STATIC_DRAW);
  const position=gl.getAttribLocation(program,'a_position');gl.enableVertexAttribArray(position);gl.vertexAttribPointer(position,2,gl.FLOAT,false,0,0);
  const resolution=gl.getUniformLocation(program,'u_resolution'),time=gl.getUniformLocation(program,'u_time');
  gl.uniform3fv(gl.getUniformLocation(program,'u_colors[0]'),new Float32Array([.0431372549,.062745098,.1490196078,.2392156863,.2745098039,.9098039216,.6941176471,.5490196078,1,1,.8392156863,.9058823529]));
  let frame=0,disposed=false,inView=true;const start=performance.now();const motion=window.matchMedia('(prefers-reduced-motion: reduce)');
  function draw(now:number){frame=0;if(disposed||document.hidden||!inView||gl!.isContextLost())return;const rect=canvas!.getBoundingClientRect(),dpr=Math.min(window.devicePixelRatio||1,1.5);const scale=Math.min(dpr,Math.sqrt(1_000_000/Math.max(1,rect.width*rect.height)));const width=Math.max(1,Math.round(rect.width*scale)),height=Math.max(1,Math.round(rect.height*scale));if(canvas!.width!==width||canvas!.height!==height){canvas!.width=width;canvas!.height=height;gl!.viewport(0,0,width,height);}gl!.uniform2f(resolution,width,height);gl!.uniform1f(time,motion.matches?0:(now-start)/1000*.86);gl!.drawArrays(gl!.TRIANGLES,0,3);if(!motion.matches)wake();}
  function wake(){if(!disposed&&!frame&&!document.hidden&&inView)frame=requestAnimationFrame(draw);}
  const resize=new ResizeObserver(wake);resize.observe(canvas);
  const intersection=new IntersectionObserver(([entry])=>{inView=entry.isIntersecting;if(inView)wake();else{cancelAnimationFrame(frame);frame=0;}});intersection.observe(canvas);
  function visibility(){if(document.hidden){cancelAnimationFrame(frame);frame=0;}else wake();}
  document.addEventListener('visibilitychange',visibility);motion.addEventListener('change',wake);wake();
  return()=>{disposed=true;cancelAnimationFrame(frame);resize.disconnect();intersection.disconnect();document.removeEventListener('visibilitychange',visibility);motion.removeEventListener('change',wake);gl.deleteBuffer(buffer);gl.deleteProgram(program);};
 },[]);
 return <canvas ref={ref} className={className} aria-hidden="true"/>;
}
